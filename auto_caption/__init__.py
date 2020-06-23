import re
import os
import sys
import json
import wave
import vosk
import nnsplit
import requests
import shutil

from pathlib import Path
from tqdm import tqdm
from argparse import ArgumentParser
from moviepy.editor import VideoFileClip
from pydub import AudioSegment
from tempfile import NamedTemporaryFile
from zipfile import ZipFile


def extract_audio(video_path, wav_path):

    video = VideoFileClip(video_path)
    video.audio.write_audiofile(wav_path)


def combine_stereos(wav_path):

    audio = AudioSegment.from_file(wav_path)
    channels = audio.split_to_mono()
    sum(channels).export(wav_path, format="wav")


def get_model_path():

    return "{}/.auto-caption/models".format(Path.home())


def download_model(lang='en'):

    urls = {
        "en":
        "https://github.com/daanzu/kaldi-active-grammar/releases/download/v1.4.0/vosk-model-en-us-daanzu-20200328.zip"
    }

    os.makedirs(get_model_path(), exist_ok=True)

    if not os.path.isdir("{}/{}".format(get_model_path(), lang)):

        with NamedTemporaryFile(suffix='.zip', delete=True) as zip_file:

            resp = requests.get(urls[lang], stream=True)
            total = int(resp.headers.get('content-length', 0))

            with open(zip_file.name, 'wb') as file, tqdm(
                    desc="Download model({})".format(lang),
                    total=total,
                    unit='iB',
                    unit_scale=True,
                    unit_divisor=1024,
            ) as bar:
                for data in resp.iter_content(chunk_size=1024):
                    size = file.write(data)
                    bar.update(size)

            zf = ZipFile(zip_file.name, 'r')
            zf.extractall(get_model_path())
            zf.close()

            name = re.sub("\.zip$", "", urls[lang].split("/")[-1])

            shutil.move("{}/{}".format(get_model_path(), name),
                        "{}/{}".format(get_model_path(), lang))


def recognize_speech(wav_path, lang="en", buffer_size=4000):

    download_model(lang)

    vosk.SetLogLevel(-1)

    wav_file = wave.open(wav_path, "rb")

    recognizer = vosk.KaldiRecognizer(
        vosk.Model("{}/{}".format(get_model_path(), lang)),
        wav_file.getframerate())

    words = []

    for index in tqdm(range(0, wav_file.getnframes(), buffer_size)):

        frames = wav_file.readframes(buffer_size)

        if recognizer.AcceptWaveform(frames):

            result = json.loads(recognizer.Result())

            if len(result["text"]) > 0:

                for token in result["result"]:
                    words.append({
                        "start": token["start"],
                        "end": token["end"],
                        "text": token["word"],
                    })

    return words


def segment_setences(words, lang="en"):

    content = " ".join(map(lambda word: word["text"], words))

    sentences = []

    left = 0

    for tokens2d in tqdm(nnsplit.NNSplit(lang).split([content])):
        for tokens in tokens2d:

            text = "".join(
                map(lambda token: token.text + token.whitespace,
                    tokens)).strip()

            right = min(len(words), left + len(tokens)) - 1

            while right > 0 and not text.endswith(words[right]["text"]):
                right -= 1

            sentences.append({
                "start": words[left]["start"],
                "end": words[right]["end"],
                "text": text
            })

            left = right + 1

    return sentences


def time2str(x):

    return "{hour:02d}:{minute:02d}:{second:02d},{millisecond}".format(
        hour=int(x) // 3600,
        minute=(int(x) // 60) % 60,
        second=int(x) % 60,
        millisecond=int(x * 1000) % 1000)


def write_srt_file(sentences, srt_path):

    with open(srt_path, "w") as srt_file:

        for index, sentence in enumerate(sentences):
            srt_file.write("{}\n{} --> {}\n{}\n\n".format(
                index + 1, time2str(sentence["start"]),
                time2str(sentence["end"]), sentence["text"]))


def auto_caption(video_path, srt_path, lang='en'):

    with NamedTemporaryFile(suffix='.wav', delete=True) as wav_file:

        extract_audio(video_path, wav_file.name)

        combine_stereos(wav_file.name)

        words = recognize_speech(wav_file.name, lang=lang)

        sentences = segment_setences(words)

        write_srt_file(sentences, srt_path)


def main():

    args_parser = ArgumentParser()

    args_parser.add_argument("video")
    args_parser.add_argument("--output")

    args = args_parser.parse_args()

    output = args.output if args.output else re.sub("\.[^\.]+$", ".srt",
                                                    args.video)

    auto_caption(args.video, output, lang="en")
