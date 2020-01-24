#!/usr/bin/env python

# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Google Cloud Speech API sample application using the streaming API.

NOTE: This module requires the dependencies `pyaudio` and `termcolor`.
To install using pip:

    pip install pyaudio
    pip install termcolor

Example usage:
    python transcribe_streaming_infinite.py



How to improve:
   don't stop until having recognized a phrase completely. This will stop the service from sending audio that is going to be re-sent anyway.
"""

# [START speech_transcribe_infinite_streaming]

import time
import re
import sys

# uses result_end_time currently only avaialble in v1p1beta, will be in v1 soon
from google.cloud import speech_v1p1beta1 as speech
import pyaudio
from six.moves import queue
import threading
import queue
from pydub import AudioSegment
from pydub.utils import make_chunks
from google.cloud.speech import enums
from google.cloud.speech import types
import google

# Audio recording parameters
STREAMING_LIMIT = 10000
SAMPLE_RATE = 41000
CHUNK_SIZE = int(SAMPLE_RATE / 10)  # 100ms

RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[0;33m'
opened_time = None

def get_current_time():
    """Return Current Time in MS."""

    return int(round(time.time() * 1000))


class ResumableMicrophoneStream:
    """Opens a recording stream as a generator yielding the audio chunks."""

    def __init__(self, rate, chunk_size,filename):
        self._rate = rate
        self.chunk_size = chunk_size
        self._num_channels = 1
        self._buff = queue.Queue()
        self.closed = True
        self.previous_start_time=-1
        self.start_time = get_current_time()
        self.restart_counter = 0
        self.audio_input = []
        self.last_audio_input = []
        self.result_end_time = 0
        self.is_final_end_time = 0
        self.final_request_end_time = 0
        self.bridging_offset_of_current_round = 0
        self.last_transcript_was_final = False
        self.new_stream = True
        self._audio_interface = pyaudio.PyAudio()
        self._audio_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            channels=self._num_channels,
            rate=self._rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            # Run the audio stream asynchronously to fill the buffer object.
            # This is necessary so that the input device's buffer doesn't
            # overflow while the calling thread makes network requests, etc.
            stream_callback=self._fill_buffer,
        )

        self.in_buffer = queue.Queue() # threadsafe queue
        self.filename = filename
        self.continue_without_history= False
       
    def __enter__(self):
        print(self.filename)
        print("")
        thread= threading.Thread(target=self.simulate_record_and_store_in_buffer,args=(self.filename,self.in_buffer,))
        thread.start()
        self.closed = False
        return self

    def __exit__(self, type, value, traceback):

        self._audio_stream.stop_stream()
        self._audio_stream.close()
        self.closed = True
        # Signal the generator to terminate so that the client's
        # streaming_recognize method will not block the process termination.
        self._buff.put(None)
        self._audio_interface.terminate()

    def _fill_buffer(self, in_data, *args, **kwargs):
        """Continuously collect data from the audio stream, into the buffer."""

        self._buff.put(in_data)
        return None, pyaudio.paContinue
    

    
    def audio_chunks_from_file_generator(self,filename):
        #this simulates the streaming microphone using an input file

        myaudio = AudioSegment.from_file(filename , "wav") 
        chunk_length_ms = 100 # pydub calculates in millisec
        chunks = make_chunks(myaudio, chunk_length_ms) #Make chunks of one sec

        for i, chunk in enumerate(chunks):
                #print("chunk*")
                time.sleep(0.1)
                yield chunk.raw_data
        
    
    def simulate_record_and_store_in_buffer(self,filename,in_buffer):
        
        """ takes the audio generator (in our case a simple generator from a file) and uses it to fill the buffer"""

        audio_generator = self.audio_chunks_from_file_generator(filename)
        for chunk in audio_generator:
            in_buffer.put(chunk)

    def get_next_audio_chunk(self):
        return self.in_buffer.get() # blocking get

    def get_next_audio_chunk_non_blocking(self):
        return self.in_buffer.get(False) # non_blocking get

    def generator(self):
        """Stream Audio from microphone to API and to local buffer"""

        while not self.closed:
            data = []

            if self.new_stream and self.last_audio_input:

                # use a file?
                # modified this to get to the correct point.
                chunk_time = (self.start_time-self.previous_start_time) / len(self.last_audio_input)

                if chunk_time != 0:

                    if self.bridging_offset_of_current_round < 0:
                        self.bridging_offset_of_current_round = 0

                    if self.bridging_offset_of_current_round > self.final_request_end_time:
                        self.bridging_offset_of_current_round = self.final_request_end_time

                    chunks_from_ms = round((self.final_request_end_time -
                                            self.bridging_offset_of_current_round) / chunk_time)
                    # chunks from ms are the chunks that were sent and recognized

                    self.bridging_offset_of_current_round = (round((
                        len(self.last_audio_input) - chunks_from_ms)
                                                  * chunk_time))
                    # bridging offset is the estimated time of audio that will be re-sent to 
                    # google this time
                    # note that this data does not get inserted into audio_input[].
                    # now insert self.last_audio_input[chunks_from_ms:] to data
                    for i in range(chunks_from_ms, len(self.last_audio_input)):
                        data.append(self.last_audio_input[i])
                    
                self.new_stream = False
                
            
            # TODO: continue from here biyotch

            # Use a blocking get() to ensure there's at least one chunk of
            # data, and stop iteration if the chunk is None, indicating the
            # end of the audio stream.
            #chunk = self._buff.get()

            chunk = self.get_next_audio_chunk()
            self.audio_input.append(chunk)

            if chunk is None:
                return
            data.append(chunk)
            # Now consume whatever other data's still buffered.
            while True:
                try:
                    #chunk = self._buff.get()
                    chunk = self.get_next_audio_chunk_non_blocking()

                    if chunk is None:
                        return
                    data.append(chunk)
                    self.audio_input.append(chunk)

                except queue.Empty:
                    #
                    break
            yield b''.join(data)


def listen_print_loop(responses, stream):
    """Iterates through server responses and prints them.

    The responses passed is a generator that will block until a response
    is provided by the server.

    Each response may contain multiple results, and each result may contain
    multiple alternatives; for details, see https://goo.gl/tjCPAU.  Here we
    print only the transcription for the top alternative of the top result.

    In this case, responses are provided for interim results as well. If the
    response is an interim one, print a line feed at the end of it, to allow
    the next result to overwrite it, until the response is a final one. For the
    final one, print a newline to preserve the finalized transcription.
    """
    global opened_time
    # this counts the number of phrases identified
    phrases_identified=0
    # print(stream.start_time)
    # print(get_current_time()-stream.start_time)
    try:
        
        for response in responses:
            
            # termination condition 
            if get_current_time() - stream.start_time > STREAMING_LIMIT:
                stream.previous_start_time= stream.start_time
                stream.start_time = get_current_time()
                break

            
            if phrases_identified == 2:
                stream.previous_start_time= stream.start_time
                sys.stdout.write("passed" + str(get_current_time()-stream.start_time) + '\n')
                stream.start_time = get_current_time()
                break

            if not response.results:
                continue

            result = response.results[0]

            if not result.alternatives:
                continue

            transcript = result.alternatives[0].transcript

            result_seconds = 0
            result_nanos = 0

            if result.result_end_time.seconds:
                result_seconds = result.result_end_time.seconds

            if result.result_end_time.nanos:
                result_nanos = result.result_end_time.nanos

            stream.result_end_time = int((result_seconds * 1000)
                                        + (result_nanos / 1000000))

            corrected_time = (stream.result_end_time - stream.bridging_offset_of_current_round
                            + (STREAMING_LIMIT * stream.restart_counter))
            
            # Display interim results, but with a carriage return at the end of the
            # line, so subsequent lines will overwrite them.

            if result.is_final:
                phrases_identified+=1
                sys.stdout.write(GREEN)
                sys.stdout.write('\033[K')
                sys.stdout.write(str(corrected_time) + ': ' + transcript + '\n')
                #sys.stdout.write(str(get_current_time()-start_time) + '\n')
                stream.is_final_end_time = stream.result_end_time
                stream.last_transcript_was_final = True

                # Exit recognition if any of the transcribed phrases could be
                # one of our keywords.
                if re.search(r'\b(exit|quit)\b', transcript, re.I):
                    sys.stdout.write(YELLOW)
                    sys.stdout.write('Exiting...\n')
                    stream.closed = True
                    break

            else:
                sys.stdout.write(RED)
                sys.stdout.write('\033[K')
                sys.stdout.write(str(corrected_time) + ': ' + transcript + '\r')

                stream.last_transcript_was_final = False
    except google.api_core.exceptions.DeadlineExceeded:
        print("got deadline exceeded error, restarting the connection..")
        # clear the buffer and restart everything
        stream.previous_start_time= stream.start_time
        stream.start_time = get_current_time()
        stream.continue_without_history = True
              


def main():
    """start bidirectional streaming from microphone input to speech API"""
    global opened_time
    client = speech.SpeechClient()
    config = speech.types.RecognitionConfig(
        encoding=speech.enums.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=SAMPLE_RATE,
        language_code='el-GR',
        max_alternatives=1,
        audio_channel_count = 2)
    streaming_config = speech.types.StreamingRecognitionConfig(
        config=config,
        interim_results=True)
    filename= "out4.wav"
    mic_manager = ResumableMicrophoneStream(SAMPLE_RATE, CHUNK_SIZE, filename)
    print(mic_manager.chunk_size)
    sys.stdout.write(YELLOW)
    sys.stdout.write('\nListening, say "Quit" or "Exit" to stop.\n\n')
    sys.stdout.write('End (ms)       Transcript Results/Status\n')
    sys.stdout.write('=====================================================\n')
    with mic_manager as stream:

        opened_time = get_current_time()
        while not stream.closed:
            sys.stdout.write(YELLOW)
            sys.stdout.write('\n' + str(
                get_current_time()-opened_time) + ': NEW REQUEST\n')

            stream.audio_input = []
            audio_generator = stream.generator()

            requests = (speech.types.StreamingRecognizeRequest(
                audio_content=content)for content in audio_generator)

            responses = client.streaming_recognize(streaming_config,
                                                   requests)

            # Now, put the transcription responses to use.
            listen_print_loop(responses, stream)

            if stream.result_end_time > 0:
                stream.final_request_end_time = stream.is_final_end_time
            stream.result_end_time = 0
            stream.last_audio_input = []
            if stream.continue_without_history == False:
                stream.last_audio_input = stream.audio_input
            else:
                ## need to handle this better, perhaps include noise that has not been repeated.
                stream.continue_without_history=False
                stream.last_audio_input = stream.last_audio_input[-20:]
            stream.audio_input = []
            stream.restart_counter = stream.restart_counter + 1

            if not stream.last_transcript_was_final:
                sys.stdout.write('\n')
            stream.new_stream = True


if __name__ == '__main__':

    main()

# [END speech_transcribe_infinite_streaming]
