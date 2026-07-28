from datetime import datetime
import os
import re
import queue
import string
import subprocess
import tempfile
import threading
import logging
import shutil
import time
from functools import cached_property, cache
from enum import Enum
from typing import Callable
import sounddevice as sd  # type: ignore[import-untyped]
from textual.app import App, ComposeResult, Binding
from textual.widgets import Header, Footer, Input, Button, Label
from textual.containers import VerticalScroll, VerticalGroup, HorizontalGroup

from msoc import Sound, search, SearchMode


logger = logging.getLogger()


Channels = int
SampleRate = float
Duration = float

ThreadId = int


class AudioPlayerState(Enum):
    LOADING = 1
    PLAYING = 2
    STOPPED = 3


class AudioPlayer:
    BUFFER_SIZE = 250
    BLOCK_SIZE = 512

    audio_ffmpeg_pattern = re.compile(r'^Stream #\d+:\d+:\s+Audio:.*?,\s+(\d+)\s+Hz,\s+([^,]+)')
    duration_ffmpeg_pattern = re.compile(r'^Duration: (\d+:\d{2}:\d{2}\.\d{2}), start: [\d.]+, bitrate:')
    channels_map = {
        'mono': 1,
        'stereo': 2,
        '2.1': 3,
        '5.1': 6,
        '7.1': 8
    }

    def __init__(self, 
                 on_play_state_change: Callable[[ThreadId, AudioPlayerState], None] | None = None, 
                 on_duration: Callable[[ThreadId, Duration], None] | None = None
                ):
        self._on_play_state_change = on_play_state_change
        self._on_duration = on_duration

        self.current_sound: Sound | None = None

        self.buffer_queue: queue.Queue[bytes] = queue.Queue(maxsize=self.BUFFER_SIZE)
        self._ffmpeg_read_file_process: subprocess.Popen | None = None
        self._download_process: subprocess.Popen | None = None
        self.sounddevice_stream: sd.RawOutputStream | None = None
        self.play_thread: threading.Thread | None = None
        self.download_thread: threading.Thread | None = None

        self._state = AudioPlayerState.STOPPED

        self._temp_dir = tempfile.mkdtemp(prefix="msoc_")
        # url: path
        self._download_paths: dict[str, str] = {}
        # url: is_download_success
        self._download_complete: dict[str, bool] = {}
        # url: is_wait_download_to_temp_path
        self._wait_download: dict[str, bool] = {}

    @staticmethod
    def _get_sound_filename(sound: Sound) -> str:
        specific_symbols = string.punctuation.replace(',','')

        def delete_specific_symbols(text: str) -> str:
            return text.translate(str.maketrans('', '', specific_symbols))

        artist_title = delete_specific_symbols(sound.artist or 'unknown')
        sound_title = delete_specific_symbols(sound.title)
        
        return f"{artist_title} - {sound_title}.mp3"

    def _callback(self, outdata, frames, time, status):
        if status:
            logger.warning(f"Audio stream status: {status}")

        try:
            data = self.buffer_queue.get_nowait()
        except queue.Empty:
            outdata[:] = b"\x00" * len(outdata)
            return

        if len(data) != len(outdata):
            # На случай рассинхрона (редко, но бывает при смене трека)
            logger.error("Audio data size mismatch. Filling with silence.")
            outdata[:] = b"\x00" * len(outdata)
            return

        outdata[:] = data

    @cached_property
    def output_device(self):
        try:
            sd.query_devices("pipewire")
            return "pipewire"
        except ValueError:
            return sd.default.device[1]

    @property
    def state(self):
        return self._state 

    @state.setter
    def state(self, value: AudioPlayerState):
        if not isinstance(value, AudioPlayerState):
            raise ValueError(f'Неверный тип для state: {type(value)}')
        
        self._state = value
        if self._on_play_state_change:
            self._on_play_state_change(threading.get_ident(), value)

    @staticmethod
    @cache
    def _get_ffprobe_info(filepath: str) -> tuple[Channels, SampleRate, Duration] | None:
        probe_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=channels,sample_rate,duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            filepath,
        ]

        try:
            probe_out = (
                subprocess.check_output(probe_cmd, stderr=subprocess.PIPE)
                .decode()
                .splitlines()
            )
        except subprocess.CalledProcessError:
            logger.error(
                "Произошла ошибка при получении метаданных трека с помощью ffprobe",
                exc_info=True,
            )
            return None

        samplerate = float(probe_out[0])
        channels = int(probe_out[1])
        duration = float(probe_out[2])

        return channels, samplerate, duration

    def _parse_metadata_sound(self) -> tuple[Channels, SampleRate, Duration] | None:
        if not self._download_process:
            raise

        if not self._download_process.stderr:
            raise

        duration_raw = None
        sample_rate = None
        channels_name = None

        for raw_line in self._download_process.stderr: 
            line = raw_line.decode().strip()
            if duration_raw is None:
                if m := self.duration_ffmpeg_pattern.match(line):
                    duration_raw = m.group(1)

            if sample_rate is None:
                if m := self.audio_ffmpeg_pattern.match(line):
                    sample_rate = m.group(1)
                    channels_name = m.group(2)

            if duration_raw is not None and sample_rate is not None:
                break
        if not (
            isinstance(duration_raw, str) 
            and isinstance(channels_name, str) 
            and isinstance(sample_rate, str)
        ):
            raise ValueError('Получены неверные типы данных при парсинге ffmpeg stderr...')

        duration = datetime.strptime(duration_raw, '%H:%M:%S.%f')
        duration_sec = duration.hour * 60 * 60 + duration.minute * 60 \
            + duration.second + duration.microsecond / 1000000
    
        channels = self.channels_map.get(channels_name)
        if not channels:
            raise ValueError(f'Неизвестный channels_name: {channels_name}')

        return channels, float(sample_rate), duration_sec

    def _stream_play_ffmpeg(self, sound_filepath: str, channels: Channels, samplerate: SampleRate):
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",  # Перезаписывать sound_filepath без вопросов
            "-i", sound_filepath,
            # для sounddeivce (тз байтов данных в числа с плавающей точкой)
            "-f", "f32le", "-acodec", "pcm_f32le", "-ac", str(channels), "-ar", str(samplerate), "pipe:1",
            # скрываем большую часть логов (кроме ошибок)
            "-v", "error"
        ]

        self._ffmpeg_read_file_process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE)
        process_stdout = self._ffmpeg_read_file_process.stdout
        # For mypy
        if not process_stdout:
            raise ValueError("ffmpeg process stdout is None")

        self.sounddevice_stream = sd.RawOutputStream(
            samplerate=samplerate,
            blocksize=self.BLOCK_SIZE,
            channels=channels,
            dtype="float32",
            callback=self._callback,
            device=self.output_device,
        )
        read_size = self.BLOCK_SIZE * channels * self.sounddevice_stream.samplesize

        # Первичная буферизация
        for _ in range(self.BUFFER_SIZE):
            data = process_stdout.read(read_size)
            if not data:
                break
            self.buffer_queue.put_nowait(data)

        self.state = AudioPlayerState.PLAYING

        with self.sounddevice_stream:
            while self.state is AudioPlayerState.PLAYING:
                data = process_stdout.read(read_size)
                if not data:  # Поток закончился
                    break

                while self.state is AudioPlayerState.PLAYING:
                    try:
                        self.buffer_queue.put(data, timeout=0.1)
                        break
                    except queue.Full:
                        logger.error(
                            "Audio buffer overflow! Dropping data. This should not happen."
                        )

    def _worker(self):
        try:
            sound = self.current_sound
            if sound is None:
                logger.error("No current sound to download for")
                raise
            
            url = sound.url
            sound_path = self._download_paths.get(url)

            if sound_path and self._download_complete.get(url, False) and os.path.exists(sound_path):
                probe_info = self._get_ffprobe_info(sound_path)
            else:
                # Формируем путь для временного файла
                sound_path = os.path.join(
                    self._temp_dir,
                    self._get_sound_filename(sound)
                )

                # Создаем пустой файл
                with open(sound_path, "wb") as fp:
                    pass

                self._download_paths[url] = sound_path
                self._download_complete[url] = False

                self.download_thread = threading.Thread(
                    target=self._download_direct_ffmpeg, 
                    args=(sound, sound_path),
                    daemon=True
                )
                self.download_thread.start()
            
                # Ждём первые 128 КБ для MP3 128kbps
                while os.path.getsize(sound_path) <= 1024 * 128:
                    if self.state is not AudioPlayerState.LOADING:
                        return
                    time.sleep(0.1)

                probe_info = self._parse_metadata_sound()

            if not probe_info:
                raise ValueError('Не удалось получить метаданные о треке')

            channels, samplerate, duration = probe_info

            if self._on_duration:
                self._on_duration(threading.get_ident(), duration)

            # Запускаем проигрывание локального файла с помощью ffmpeg и sounddevice
            self._stream_play_ffmpeg(sound_path, channels, samplerate)
            
            logger.info("Воспроизведение завершено: %s", sound_path)
        except:
            logger.error('Произошла ошибка в _worker', exc_info=True)
        finally:
            if self.state != AudioPlayerState.STOPPED:
                self.state = AudioPlayerState.STOPPED

            self._abort_sounddevice_stream()
            self._clear_buffer_queue()
            self._kill_ffmpeg_read_file_process()

    def _kill_ffmpeg_read_file_process(self):
        if not self._ffmpeg_read_file_process:
            return
        
        self._ffmpeg_read_file_process.kill()
        self._ffmpeg_read_file_process.wait()
        self._ffmpeg_read_file_process = None

    def _abort_sounddevice_stream(self):
        if not self.sounddevice_stream:
            return
        
        try:
            self.sounddevice_stream.stop()
            self.sounddevice_stream.abort()
            self.sounddevice_stream.close()
        except Exception:
            logger.error('Произошла ошибка при закрытии sounddevice стрима', exc_info=True)

        self.sounddevice_stream = None

    def _clear_buffer_queue(self):
        self.buffer_queue = queue.Queue(maxsize=self.BUFFER_SIZE)

    def _kill_download_process(self):
        if not self._download_process:
            return
        
        self._download_process.kill()
        self._download_process.wait()
        self._download_process = None

    def play(self, sound: Sound):
        self.state = AudioPlayerState.LOADING
        self.current_sound = sound

        self.play_thread = threading.Thread(target=self._worker, daemon=True)
        self.play_thread.start()

    def stop(self):
        """Остановка воспроизведения"""
        self.state = AudioPlayerState.STOPPED
        if self.play_thread and self.play_thread.is_alive():
            self.play_thread.join()
        
        url = self.current_sound.url if self.current_sound else None
        if self.download_thread and not self._wait_download.get(url, False):
            self._kill_download_process()
            self.download_thread.join()

    def download_sound(self, sound: Sound) -> str | None:
        """
        Скачивание файла (запускается в отдельном потоке, отличном от self.download_thread)
        """
        url = sound.url
        dest = os.path.join(
            os.getcwd(),
            self._get_sound_filename(sound),
        )
        
        temp_path = self._download_paths.get(url)
        is_complete = self._download_complete.get(url, False)
        is_currently_playing = (
            self.state is not AudioPlayerState.STOPPED
            and self.current_sound
            and self.current_sound.url == url
        )

        def copy_soundfile(source: str, dest: str) -> str | None:
            try:
                # copy2 в отличие от copy пытается сохранить метаданные (владельца, группу, дата создания и т д)
                shutil.copy2(source, dest)
                logger.info("Скопировано из кэша в: %s", dest)
                return dest
            except Exception:
                logger.exception("Ошибка копирования из кэша")
                return None

        # Если Трек уже полностью загружен фоновым ffmpeg, то просто копируем его в текущую директорию
        if temp_path and is_complete and os.path.exists(temp_path):
            return copy_soundfile(temp_path, dest)

        # Если трек сейчас играет, то мы не можем копировать незавершенный файл.
        if temp_path and is_currently_playing:
            logger.info("Трек играет, ожидаем загрузки с последующем копированием в dest...")
            self._wait_download[url] = True
            while True:
                is_complete = self._download_complete.get(url, False)
                if is_complete:
                    del self._wait_download[url]
                    return copy_soundfile(temp_path, dest)
                
        # Если трек не играет и не загружен, загружаем с нуля.
        dest_path = self._download_direct_ffmpeg(sound, dest)
        if dest_path:
            self._download_paths[url] = dest_path
        return dest_path

    def _download_direct_ffmpeg(self, sound: Sound, dest: str) -> str | None:
        """Быстрая загрузка без декодирования в PCM, только для сохранения файла."""
        cmd = [
            "ffmpeg", "-y", "-reconnect", "1", "-reconnect_streamed", "1",
            "-i", sound.url, "-c:a", "copy", dest, '-v', 'info'
        ]
        self._download_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        while True:
            if self._download_process is None:
                return None
            
            returncode = self._download_process.poll()
            if returncode is None:
                time.sleep(0.5)
                continue

            if returncode == 0:
                break

            logger.error(f'ffmpeg процесс по скачиванию файла завершился с ошибкой: {returncode}')
            return None

        logger.info("Прямая загрузка завершена: %s", dest)
        self._download_complete[sound.url] = True
        return dest



class DurationLabel(Label):
    pass


class SoundWidget(VerticalGroup):
    def __init__(self, sound: Sound, player: AudioPlayer, **widget_kwargs):
        self.app: MsocApp
        self.sound = sound
        self.player = player
        super().__init__(**widget_kwargs)

    def compose(self) -> ComposeResult:
        with HorizontalGroup(classes="sound-row"):
            yield Button("▶", id="toggle-play", variant="success", classes="play-btn")
            with VerticalGroup(classes="sound-info"):
                yield Label(self.sound.title, classes="song-title")
                yield Label(self.sound.artist or "", classes="song-artist")
                yield Label(self.sound._engine or 'none', classes='song-engine')
            yield DurationLabel("", classes="duration-label")
            yield Button("Download", id="download", classes="download-btn")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "toggle-play":
            self._action_toggle_play(event)
        elif event.button.id == "download":
            self._action_download(event)

    def set_duration(self, duration_sec: Duration):
        minutes = int(duration_sec // 60)
        seconds = int(duration_sec % 60)
        self.query_one(DurationLabel).update(f"{minutes:02d}:{seconds:02d}")

    def _action_download(self, event: Button.Pressed):
        event.button.label = "..."
        event.button.disabled = True

        def _do_download():
            path = self.player.download_sound(self.sound)
            self.app.call_from_thread(self._on_download_done, path)

        threading.Thread(target=_do_download, daemon=True).start()

    def _on_download_done(self, path: str | None):
        btn = self.query_one("#download", Button)
        if path:
            btn.label = "✓"
            btn.variant = "success"
        else:
            btn.label = "✗"
            btn.variant = "error"
        btn.disabled = False

    def _action_toggle_play(self, event: Button.Pressed):
        if self.app.current_sound_widget == self and self.player.state is not AudioPlayerState.STOPPED:
            self.player.stop()
            self.change_play_button_icon("▶")
        else:
            self.player.stop()
            self.app.current_sound_widget = self
            self.change_play_button_icon("...")
            self.player.play(self.sound)

    def change_play_button_icon(self, icon: str):
        """Изменение иконки кнопки."""
        self.query_one("#toggle-play", Button).label = icon


class MsocApp(App):
    CSS = """
    SoundWidget {
        height: auto;
        padding: 0 1;
        border: solid green;
    }
    .sound-row {
        height: auto;
        width: 100%;
        padding: 0;
    }
    .play-btn {
        width: 5;
        min-width: 3;
        margin-right: 1;
    }
    .sound-info {
        height: auto;
        width: 1fr;
    }
    .song-title {
        text-style: bold;
        padding: 0;
        min-height: 1;
    }
    .song-artist {
        opacity: 0.7;
        padding: 0;
        min-height: 1;
    }
    .song-engine {
        opacity: 0.8;
        padding: 0;
        min-height: 1;
        text-style: italic;
    }
    .duration-label {
        width: 6;
        content-align: center middle;
        opacity: 0.6;
    }
    .download-btn {
        width: 10;
        margin-left: 1;
    }
    """

    suffix_title_pattern = re.compile(r' \([a-zA-Z]* mode\)$')
    button_play_icons = {
        AudioPlayerState.LOADING: '...',
        AudioPlayerState.PLAYING: "⏸",
        AudioPlayerState.STOPPED: "▶",
    }

    BINDINGS = [
        Binding('m', 'toggle_search_mode', "Change Search Mode")
    ]

    def __init__(self, search_mode: SearchMode = SearchMode.Fast):
        super().__init__()
        self.player = AudioPlayer(
            on_play_state_change=self._on_player_state_change,
            on_duration=self._on_player_duration,
        )
        self.search_mode = search_mode
        self.current_sound_widget: SoundWidget | None = None
        self.update_title()

    def _on_player_state_change(self, thread_id: ThreadId, state: AudioPlayerState):
        if thread_id == threading.get_ident():
            self._update_widget_play_state(state)
            return
        
        self.call_from_thread(self._update_widget_play_state, state)

    def _on_player_duration(self, thread_id: ThreadId, duration: Duration):
        if thread_id == threading.get_ident():
            self._set_widget_duration(duration)
            return
        
        self.call_from_thread(self._set_widget_duration, duration)

    def _update_widget_play_state(self, state: AudioPlayerState):
        if not self.current_sound_widget:
            logger.warning('_update_widget_play_state был вызван, когда current_sound_widget = None', stack_info=True)
            return
        
        icon = self.button_play_icons.get(state)
        if not icon:
            logger.warning(f'Неизвестное состояние? WTF: {state}')
            return
        
        self.current_sound_widget.change_play_button_icon(icon)

    def _set_widget_duration(self, duration: Duration):
        if not self.current_sound_widget:
            logger.warning('_set_widget_duration был вызван, когда current_sound_widget = None', stack_info=True)
            return
        
        self.current_sound_widget.set_duration(duration)

    def update_title(self, title: str | None = None):
        if not title:
            title = self.suffix_title_pattern.sub('', self.title)

        self.title = title + f' ({self.search_mode.value.title()} mode)'

    def action_toggle_search_mode(self):
        self.search_mode = SearchMode.Fast if self.search_mode == SearchMode.Full else SearchMode.Full
        self.update_title()

    def on_input_submitted(self, event: Input.Submitted):
        if event.control.id != "search":
            return
        self.update_title("Идет поиск...")
        event.control.disabled = True
        self.run_worker(self.search_task(event.value), name="search")

    async def search_task(self, query: str):
        list_sounds_container = self.query_one("#list-sounds")
        list_sounds_container.remove_children()

        async for sound in search(query, mode=self.search_mode):
            sound_widget = SoundWidget(sound, self.player)
            await list_sounds_container.mount(sound_widget)

        self.update_title("Поиск завершен")
        self.query_one("#search").disabled = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="Введите поисковой запрос", id="search")
        yield VerticalScroll(id="list-sounds")
        yield Footer()

    def on_unmount(self, event):
        self.player.stop()


if __name__ == "__main__":
    logging.basicConfig(
        filename="journal_app.log",
        filemode="w",
        level=logging.DEBUG,
        format="[%(asctime)s - %(name)s] - %(levelname)s - %(message)s",
    )

    app = MsocApp()
    app.run()
