from functools import cache
import json
import subprocess
import asyncio
import logging
import threading
import queue
import sounddevice as sd# type: ignore
from msoc import Sound, search

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Button, Label
from textual.containers import VerticalScroll, HorizontalGroup, VerticalGroup


logger = logging.getLogger()


class SoundWidget(HorizontalGroup):
    def __init__(self, player: "AudioPlayer", sound: Sound, **widget_kwargs):
        self.sound = sound
        self.player = player
        
        super().__init__(**widget_kwargs)

    def on_button_pressed(self, event: Button.Pressed):
        if event.control.id != 'toggle-play':
            return
        
        self.player.toggle_play(self)

    def change_icon_button_play(self, icon: str):
        self.query_one('#toggle-play').label = icon  # type: ignore

    def compose(self) -> ComposeResult:
        yield Button('▶', id='toggle-play')
        yield VerticalGroup(
            Label(self.sound.title, variant='accent'),
            Label(self.sound.artist or '')
        )


Duration = float
Channels = int
SampleRate = int


class AudioPlayer:
    BLOCKSIZE = 1024
    BUFFERSIZE = 50

    def __init__(self) -> None:
        self.current_control: SoundWidget | None        = None
        self._thread: threading.Thread | None           = None

        # For Worker
        self._ffmpeg_process: subprocess.Popen | None   = None
        self._queue: queue.Queue                        = queue.Queue(maxsize=self.BUFFERSIZE)
        self._stream: sd.RawOutputStream | None         = None

    def toggle_play(self, control: SoundWidget):
        # Если у нас уже что то воспроизводиться то в любом случае останавливаем
        if self.current_control:
            self._stop()

        # Если пользователь нажал на ту же кнопку, что и ранее, то просто выходим с функции
        if control == self.current_control:
            self.current_control = None
            return
        
        # В ином случае начинаем воспроизводить другую песню
        self.current_control = control
        self.current_control.change_icon_button_play('..')

        self._thread = threading.Thread(target=self._worker)
        self._thread.start()

    def _stop(self):
        if not self.current_control:
            logger.warning('Ничего не проигрывается (current_control пуст)')
            return

        self._thread.join()
        if self._ffmpeg_process:
            self._ffmpeg_process.kill()
            self._queue.join()

        self.current_control.change_icon_button_play('▶')

    def _worker(self):
        download_url = self.current_control.sound.url
        song_info = self._get_ffprobe_info(download_url)
        if not song_info:
            logger.error('Мета данные о треке не были получены')
            return
        
        self.current_control.change_icon_button_play('⏸')

        self._ffmpeg_stream(download_url, song_info[0], song_info[1])

        app = self.current_control.app
        app.call_from_thread(lambda: self.current_control.change_icon_button_play('▶'))
        self.current_control = None
    
    @cache
    def device(self):
        try:
            sd.query_devices('pipewire')
            return 'pipewire'
        except ValueError:
            return sd.default.device[1]
        
    @staticmethod
    def _get_ffprobe_info(url: str) -> tuple[SampleRate, Channels, Duration] | None:
        ffprobe_cmd = [
            "ffprobe", "-of", "json", "-show_streams", '-loglevel', 'quiet', url
        ]

        try:
            raw_song_info = subprocess.check_output(ffprobe_cmd, text=True)
        except subprocess.CalledProcessError:
            logger.error('Не удалось получить информацию о треке с помощью ffprobe', exc_info=True)
            return None
        
        try:
            song_info = json.loads(raw_song_info)
        except json.JSONDecodeError:
            logger.error('Не удалось распарсить вывод ffprobe в json формат', exc_info=True)
            return None

        streams = song_info.get('streams')
        if len(streams) == 0:
            logger.error(f'ffprobe выдал пустой ответ (без streams): {song_info}')
            return None
        
        stream = streams[0]

        if stream.get('codec_type') != 'audio':
            logger.error(f'The stream must be an audio stream: {stream}')
            return None

        try:
            sample_rate = int(stream.get('sample_rate'))
            channels = int(stream.get('channels'))
            duration = float(stream.get('duration'))
        except:
            logger.error(f'Произошла ошибка преобразования строк в числа, {sample_rate=}, {channels=}, {duration=}', exc_info=True)
            return None

        return sample_rate, channels, duration
    
    def _callback_sounddevice(self, outdata, frames, time, status):
        if status.output_underflow:
            raise sd.CallbackAbort
        try:
            data = self.q.get_nowait()
        except queue.Empty:
            raise sd.CallbackAbort
        
        if len(data) != len(outdata):
            raise sd.CallbackAbort
            
        outdata[:] = data

    def _ffmpeg_stream(self, url: str, sample_rate: SampleRate, channels: Channels):
        ffmpeg_cmd = [
            'ffmpeg', '-i', url, '-f', 'f32le', '-acodec', 'pcm_f32le', 
            '-ac', str(channels), '-ar', str(sample_rate), '-loglevel', 'quiet', 'pipe:'
        ]

        # FIXME: Нужен ли Lock?
        self._ffmpeg_process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE)
        ffmpeg_stdout = self._ffmpeg_process.stdout

        # NOTE: For mypy
        if not ffmpeg_stdout:
            logger.error('ffmpeg stdout is None')
            return
        
        stream = sd.RawOutputStream(
            samplerate=sample_rate, 
            channels=channels, 
            blocksize=self.BLOCKSIZE,
            callback=self._callback_sounddevice, 
            dtype='float32',
            device=self.device()
        )

        read_size = self.BLOCKSIZE * channels * stream.samplesize

        for _ in range(self.BUFFERSIZE):
            buffer_chunk = ffmpeg_stdout.read(read_size)
            self._queue.put_nowait(buffer_chunk)

        # timeout = self.BLOCKSIZE * self.BUFFERSIZE / sample_rate

        with stream:
            while True:
                buffer_chunk = ffmpeg_stdout.read(read_size)
                if not buffer_chunk:
                    logger.info('ffmpeg stdout пуст')
                    break

                self._queue.put(buffer_chunk)


class MsocApp(App):
    def __init__(self, **app_kwargs):
        self.player = AudioPlayer()

        super().__init__(**app_kwargs)

    def on_input_submitted(self, event: Input.Submitted):
        if event.control.id != 'search':
            return

        self.title = "Идет поиск..."
        event.control.disabled = True
        asyncio.create_task(self.search_task(event.value))

    def clear_sounds_container(self):
        self.query('SoundWidget').remove()

    async def search_task(self, query: str):
        self.clear_sounds_container()

        list_sounds_container = self.query_one("#list-sounds")
        
        async for sound in search(query):
            sound_widget = SoundWidget(self.player, sound)
            list_sounds_container.mount(sound_widget)

        self.title = "Поиск завершен"

        self.query_one('#search').disabled = False

    def compose(self) -> ComposeResult:
        yield Header(True)
        yield Input(placeholder='Введите поисковой запрос', id='search')
        yield VerticalScroll(id='list-sounds')
        yield Footer()
    

if __name__ == '__main__':
    logging.basicConfig(
        filename='journal_app.log',
        level=logging.DEBUG,
        format="[%(asctime)s - %(name)s] - %(levelname)s - %(message)s"
    )

    app = MsocApp()
    app.run()

