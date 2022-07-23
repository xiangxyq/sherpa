#!/usr/bin/env python3
# Copyright      2022  Xiaomi Corp.        (authors: Fangjun Kuang)
#
# See LICENSE for clarification regarding multiple authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
A client for streaming ASR recognition.

Usage:
    ./streaming_client.py \
      --server-addr localhost \
      --server-port 6006 \
      /path/to/foo.wav \
      /path/to/bar.wav

(Note: You have to first start the server before starting the client)
"""
import argparse
import asyncio
import http
import logging
from typing import List

import torchaudio
import websockets


def get_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        "--server-addr",
        type=str,
        default="localhost",
        help="Address of the server",
    )

    parser.add_argument(
        "--server-port",
        type=int,
        default=6006,
        help="Port of the server",
    )

    parser.add_argument(
        "sound_files",
        type=str,
        nargs="+",
        help="The input sound file(s) to transcribe. "
        "Supported formats are those supported by torchaudio.load(). "
        "For example, wav and flac are supported. "
        "The sample rate has to be 16kHz.",
    )

    return parser.parse_args()


async def receive_results(socket: websockets.WebSocketServerProtocol):
    partial_result = ""
    async for message in socket:
        if message == "Done":
            break
        partial_result = message
        last_20_words = partial_result.split()[-20:]
        last_20_words = " ".join(last_20_words)
        logging.info(f"Partial result (last 20 words): {last_20_words}")

    return partial_result


async def run(server_addr: str, server_port: int, test_wavs: List[str]):
    for test_wav in test_wavs:
        async with websockets.connect(
            f"ws://{server_addr}:{server_port}"
        ) as websocket:  # noqa
            logging.info(f"Sending {test_wav}")
            wave, sample_rate = torchaudio.load(test_wav)
            assert sample_rate == 16000, sample_rate

            wave = wave.squeeze(0)
            receive_task = asyncio.create_task(receive_results(websocket))

            frame_size = 4096
            sleep_time = frame_size / sample_rate  # in seconds
            start = 0
            while start < wave.numel():
                end = start + min(frame_size, wave.numel() - start)
                d = wave.numpy().data[start:end]

                await websocket.send(d)
                await asyncio.sleep(sleep_time)  # in seconds

                start += frame_size

            await websocket.send(b"Done")
            decoding_results = await receive_task
            logging.info(f"{test_wav}\n{decoding_results}")


async def main():
    args = get_args()
    assert len(args.sound_files) > 0, "Empty sound files"

    server_addr = args.server_addr
    server_port = args.server_port

    max_retry_count = 5
    count = 0
    while count < max_retry_count:
        count += 1
        try:
            await run(server_addr, server_port, args.sound_files)
            break
        except websockets.exceptions.InvalidStatusCode as e:
            print(e.status_code)
            print(http.client.responses[e.status_code])
            print(e.headers)

            if e.status_code != http.HTTPStatus.SERVICE_UNAVAILABLE:
                raise
            await asyncio.sleep(2)
        except:  # noqa
            raise


if __name__ == "__main__":
    formatter = "%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s"  # noqa
    logging.basicConfig(format=formatter, level=logging.INFO)
    asyncio.run(main())
