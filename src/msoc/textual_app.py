from functools import cached_property
import os
import queue
import re
import string
import subprocess
import tempfile
import threading
import logging
import shutil

import sounddevice as sd  # type: ignore[import-untyped]
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Button, Label
from textual.containers import VerticalScroll, VerticalGroup, HorizontalGroup

from msoc import Sound, search


logger = logging.getLogger()

Channels = int
SampleRate = float
Duration = float


class AudioPlayer:
    BUFFER_SIZE = 250
    BLOCK_SIZE = 512

    def __init__(self, app: App):
        self.app = app
        self.buffer_queue: queue.Queue[bytes] = queue.Queue(maxsize=self.BUFFER_SIZE)
        self.process: subprocess.Popen | None = None
        self.stream: sd.RawOutputStream | None = None
        self.thread: threading.Thread | None = None
        self.current_widget: SoundWidget | None = None

        self.manage_task_queue: queue.Queue[str] = queue.Queue(maxsize=1)
        self.is_playing = False

        self._temp_dir = tempfile.mkdtemp(prefix="msoc_")
        # url: path
        self._download_paths: dict[str, str] = {}
        # url: is_download_success
        self._download_complete: dict[str, bool] = {}
        
        # Блокировка для безопасной проверки статуса загрузки
        self._download_lock = threading.Lock()

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

    @staticmethod
    def _get_ffprobe_info(url: str) -> tuple[Channels, SampleRate, Duration] | None:
        probe_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=channels,sample_rate,duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            url,
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

    def _stream_play_ffmpeg(self, url: str, channels: Channels, samplerate: SampleRate, temp_path: str):
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",  # Перезаписывать temp_path без вопросов
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "2",
            "-i", url,
            # для sounddeivce (numpy тип)
            "-f", "f32le", "-acodec", "pcm_f32le", "-ac", str(channels), "-ar", str(samplerate), "pipe:1",
            # для сохранения на диск параллельно
            "-c:a", "copy", temp_path,
            # скрываем логи
            "-v", "error"
        ]

        self.process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE)
        process_stdout = self.process.stdout
        # For mypy
        if not process_stdout:
            logger.error("ffmpeg process stdout is None...")
            return

        self.stream = sd.RawOutputStream(
            samplerate=samplerate,
            blocksize=self.BLOCK_SIZE,
            channels=channels,
            dtype="float32",
            callback=self._callback,
            device=self.output_device,
        )
        read_size = self.BLOCK_SIZE * channels * self.stream.samplesize

        # Первичная буферизация
        for _ in range(self.BUFFER_SIZE):
            data = process_stdout.read(read_size)
            if not data:
                break
            self.buffer_queue.put_nowait(data)

        self.is_playing = True

        if self.current_widget:
            self.app.call_from_thread(self.current_widget.change_button_icon, "⏸")

        with self.stream:
            while self.is_playing:
                data = process_stdout.read(read_size)
                if not data:  # Поток закончился
                    break

                while self.is_playing:
                    try:
                        self.buffer_queue.put(data, timeout=0.1)
                        break
                    except queue.Full:
                        logger.error(
                            "Audio buffer overflow! Dropping data. This should not happen."
                        )

    def _worker(self, url: str):
        try:
            probe_info = self._get_ffprobe_info(url)
            if not probe_info:
                logger.error("Не удалось получить метаданные о треке...")
                return

            channels, samplerate, duration = probe_info
            widget = self.current_widget
            if widget is None:
                logger.error("No current widget to download for")
                return
            
            self.app.call_from_thread(widget.set_duration, duration)

            # Формируем путь для временного файла
            temp_path = os.path.join(
                self._temp_dir,
                self._get_sound_filename(widget.sound)
            )
            
            with self._download_lock:
                self._download_paths[url] = temp_path
                self._download_complete[url] = False

            # Запускаем ffmpeg, который будет ИГРАТЬ и СОХРАНЯТЬ одновременно
            self._stream_play_ffmpeg(url, channels, samplerate, temp_path)
            
            # FIXME: даже после join, поток завершается корректно, и поэтому даже если трек не был полностью скачен, ему выдается download_complete = True
            with self._download_lock:
                self._download_complete[url] = True
            logger.info("Фоновая загрузка завершена: %s", temp_path)

        finally:
            if not self.manage_task_queue.empty():
                self.manage_task_queue.get_nowait()
                return

            if self.current_widget:
                self.app.call_from_thread(
                    self.current_widget.change_button_icon, "▶"
                )

            self._cleanup()
            self.current_widget = None

    def _cleanup(self):
        self.is_playing = False
        if self.stream:
            try:
                self.stream.abort()
                self.stream.close()
            except Exception:
                pass

        if self.process:
            self.process.kill()
            self.process.wait()

        self.buffer_queue = queue.Queue(maxsize=self.BUFFER_SIZE)

        self.stream = None
        self.process = None

    def play(self, url: str, widget: "SoundWidget"):
        self.stop()  # Останавливаем предыдущее, если играло

        self.current_widget = widget

        self.thread = threading.Thread(target=self._worker, args=(url,), daemon=True)
        self.thread.start()

    def stop(self):
        """Остановка воспроизведения"""
        if self.thread and self.thread.is_alive():
            if self.manage_task_queue.empty():
                self.manage_task_queue.put("stop_ui")
            self.thread.join(timeout=1.5)

        self._cleanup()
        if self.current_widget:
            self.current_widget.change_button_icon("▶")

        self.current_widget = None

    def download_sound(self, sound: Sound) -> str | None:
        url = sound.url
        dest = os.path.join(
            os.getcwd(),
            self._get_sound_filename(sound),
        )
        
        with self._download_lock:
            temp_path = self._download_paths.get(url)
            is_complete = self._download_complete.get(url, False)
            is_currently_playing = (self.current_widget and self.current_widget.sound.url == url)

        # Если Трек уже полностью загружен фоновым ffmpeg, то просто копируем его в текущую директорию
        if temp_path and is_complete and os.path.exists(temp_path):
            try:
                # copy2 в отличие от copy пытается сохранить метаданные (владельца, группу, дата создания и т д)
                shutil.copy2(temp_path, dest)
                logger.info("Скопировано из кэша в: %s", dest)
                return dest
            except Exception:
                logger.exception("Ошибка копирования из кэша")

        # Если трек сейчас играет, то мы не можем копировать незавершенный файл. Запускаем отдельную загрузку с нуля.
        if is_currently_playing:
            logger.info("Трек играет, запускаем параллельную быструю загрузку...")
            return self._download_direct_ffmpeg(sound, dest)

        # Если трек не играет и не загружен, загружаем с нуля.
        return self._download_direct_ffmpeg(sound, dest)

    def _download_direct_ffmpeg(self, sound: Sound, dest: str) -> str | None:
        """Быстрая загрузка без декодирования в PCM, только для сохранения файла."""
        cmd = [
            "ffmpeg", "-y", "-reconnect", "1", "-reconnect_streamed", "1",
            "-i", sound.url, "-c:a", "copy", dest, '-v', 'error'
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("Прямая загрузка завершена: %s", dest)
            return dest
        except subprocess.CalledProcessError:
            logger.exception("Ошибка прямой загрузки через ffmpeg")
            return None


class DurationLabel(Label):
    pass


class SoundWidget(VerticalGroup):
    def __init__(self, sound: Sound, player: AudioPlayer, **widget_kwargs):
        self.sound = sound
        self.player = player
        super().__init__(**widget_kwargs)

    def compose(self) -> ComposeResult:
        with HorizontalGroup(classes="sound-row"):
            yield Button("▶", id="toggle-play", variant="success", classes="play-btn")
            with VerticalGroup(classes="sound-info"):
                yield Label(self.sound.title, classes="song-title")
                yield Label(self.sound.artist or "", classes="song-artist")
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
        # Если эта песня уже играет - останавливаем
        if self.player.current_widget == self and self.player.is_playing:
            self.player.stop()
            self.change_button_icon("▶")
        else:
            # Иначе запускаем
            event.button.label = "..."
            self.player.play(self.sound.url, self)

    def change_button_icon(self, icon: str):
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

    def __init__(self):
        super().__init__()
        self.player = AudioPlayer(self)

    def on_input_submitted(self, event: Input.Submitted):
        if event.control.id != "search":
            return
        self.title = "Идет поиск..."
        event.control.disabled = True
        self.run_worker(self.search_task(event.value), name="search")

    async def search_task(self, query: str):
        list_sounds_container = self.query_one("#list-sounds")
        list_sounds_container.remove_children()

        async for sound in search(query):
            sound_widget = SoundWidget(sound, self.player)
            await list_sounds_container.mount(sound_widget)

        self.title = "Поиск завершен"
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
        level=logging.DEBUG,
        format="[%(asctime)s - %(name)s] - %(levelname)s - %(message)s",
    )

    app = MsocApp()
    app.run()
