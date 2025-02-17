# Copyright      2022  Xiaomi Corp.        (authors: Fangjun Kuang
#                                                    Zengwei Yao)
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

import math
from typing import List, Tuple

import torch
from kaldifeat import FbankOptions, OnlineFbank, OnlineFeature

import sherpa


def unstack_states(
    states: Tuple[torch.Tensor, torch.Tensor]
) -> List[Tuple[torch.Tensor, torch.Tensor]]:
    """
    Unstack the lstm states corresponding to a batch of utterances into a list
    of states, where the i-th entry is the state from the i-th utterance.

    Args:
      states:
        A tuple of 2 elements.
        ``states[0]`` is the lstm hidden states, of a batch of utterance.
        ``states[1]`` is the lstm cell states, of a batch of utterances.

    Returns:
      A list of states.
        ``states[i]`` is a tuple of 2 elememts of i-th utterance.
        ``states[i][0]`` is the lstm hidden states of i-th utterance.
        ``states[i][1]`` is the lstm cell states of i-th utterance.
    """
    hidden_states, cell_states = states

    list_hidden_states = hidden_states.unbind(dim=1)
    list_cell_states = cell_states.unbind(dim=1)

    ans = [
        (h.unsqueeze(1), c.unsqueeze(1))
        for (h, c) in zip(list_hidden_states, list_cell_states)
    ]
    return ans


def stack_states(
    states_list: List[Tuple[torch.Tensor, torch.Tensor]]
) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    Stack list of lstm states corresponding to separate utterances into a single
    lstm state so that it can be used as an input for lstm when those utterances
    are formed into a batch.

    Args:
      state_list:
        Each element in state_list corresponds to the lstm state for a single
        utterance.
        ``states[i]`` is a tuple of 2 elememts of i-th utterance.
        ``states[i][0]`` is the lstm hidden states of i-th utterance.
        ``states[i][1]`` is the lstm cell states of i-th utterance.


    Returns:
      A new state corresponding to a batch of utterances.
      It is a tuple of 2 elements.
        ``states[0]`` is the lstm hidden states, of a batch of utterance.
        ``states[1]`` is the lstm cell states, of a batch of utterances.
    """
    hidden_states = torch.cat([s[0] for s in states_list], dim=1)
    cell_states = torch.cat([s[1] for s in states_list], dim=1)
    ans = (hidden_states, cell_states)
    return ans


def _create_streaming_feature_extractor() -> OnlineFeature:
    """Create a CPU streaming feature extractor.

    At present, we assume it returns a fbank feature extractor with
    fixed options. In the future, we will support passing in the options
    from outside.

    Returns:
      Return a CPU streaming feature extractor.
    """
    opts = FbankOptions()
    opts.device = "cpu"
    opts.frame_opts.dither = 0
    opts.frame_opts.snip_edges = False
    opts.frame_opts.samp_freq = 16000
    opts.mel_opts.num_bins = 80

    opts.frame_opts.max_feature_vectors = -1
    return OnlineFbank(opts)


class Stream(object):
    def __init__(
        self,
        context_size: int,
        subsampling_factor: int,
        initial_states: List[List[torch.Tensor]],
    ) -> None:
        """
        Args:
          context_size:
            Context size of the RNN-T decoder model.
          subsampling_factor:
            Subsampling factor of the RNN-T encoder model.
          initial_states:
            The initial states of the Emformer model. Note that the state
            does not contain the batch dimension.
        """
        self.feature_extractor = _create_streaming_feature_extractor()
        # It contains a list of 2-D tensors representing the feature frames.
        # Each entry is of shape (1, feature_dim)
        self.features: List[torch.Tensor] = []
        self.num_fetched_frames = 0  # before subsampling
        self.num_trailing_blank_frames = 0  # after subsampling

        self.states = initial_states
        self.processed_frames = 0  # before subsampling
        self.context_size = context_size
        self.subsampling_factor = subsampling_factor
        self.log_eps = math.log(1e-10)

        # increment on endpointing
        self.segment = 0

        # Number of frames decoded so far (after subsampling)
        self.frame_offset = 0  # never reset

        # frame offset within the current segment after subsampling
        self.segment_frame_offset = 0  # reset on endpointing

    def accept_waveform(
        self,
        sampling_rate: float,
        waveform: torch.Tensor,
    ) -> None:
        """Feed audio samples to the feature extractor and compute features
        if there are enough samples available.

        Caution:
          The range of the audio samples should match the one used in the
          training. That is, if you use the range [-1, 1] in the training, then
          the input audio samples should also be normalized to [-1, 1].

        Args
          sampling_rate:
            The sampling rate of the input audio samples. It is used for sanity
            check to ensure that the input sampling rate equals to the one
            used in the extractor. If they are not equal, then no resampling
            will be performed; instead an error will be thrown.
          waveform:
            A 1-D torch tensor of dtype torch.float32 containing audio samples.
            It should be on CPU.
        """
        self.feature_extractor.accept_waveform(
            sampling_rate=sampling_rate,
            waveform=waveform,
        )
        self._fetch_frames()

    def input_finished(self) -> None:
        """Signal that no more audio samples available and the feature
        extractor should flush the buffered samples to compute frames.
        """
        self.feature_extractor.input_finished()
        self._fetch_frames()

    def _fetch_frames(self) -> None:
        """Fetch frames from the feature extractor"""
        while self.num_fetched_frames < self.feature_extractor.num_frames_ready:
            frame = self.feature_extractor.get_frame(self.num_fetched_frames)
            self.features.append(frame)
            self.num_fetched_frames += 1

    def add_tail_paddings(self, n: int = 20) -> None:
        """Add some tail paddings so that we have enough context to process
        frames at the very end of an utterance.

        Args:
          n:
            Number of tail padding frames to be added. You can increase it if
            it happens that there are many missing tokens for the last word of
            an utterance.
        """
        tail_padding = torch.full(
            (1, self.feature_extractor.opts.mel_opts.num_bins),
            fill_value=self.log_eps,
            dtype=torch.float32,
        )

        self.features += [tail_padding] * n

    def endpoint_detected(
        self,
        config: sherpa.OnlineEndpointConfig,
    ) -> bool:
        """
        Args:
          config:
            Config for endpointing.
        Returns:
          Return True if endpoint is detected; return False otherwise.
        """
        frame_shift_in_seconds = (
            self.feature_extractor.opts.frame_opts.frame_shift_ms / 1000
        )

        trailing_silence_frames = (
            self.num_trailing_blank_frames * self.subsampling_factor
        )

        detected = sherpa.endpoint_detected(
            config=config,
            num_frames_decoded=self.processed_frames,
            trailing_silence_frames=trailing_silence_frames,
            frame_shift_in_seconds=frame_shift_in_seconds,
        )
        if detected:
            self.num_trailing_blank_frames = 0
            self.processed_frames = 0
            self.segment += 1
            self.segment_frame_offset = 0

        return detected
