
# test_from_file.py

from __future__ import division
import re
import argparse
import pyaudio
import logging
from six.moves import queue
from websocket import create_connection
import time
import multiprocessing
from pydub import AudioSegment
from pydub.utils import make_chunks
from google.cloud import speech
from google.cloud.speech import enums
from google.cloud.speech import types
import argparse
import os
import sys
import google





''' This script takes a single channel wav file as an argument, and
    streams it to google for transcribing 
    It can be used with flag --no_interim.
    
    Here we instantiate an ASR client. Then main() calls method run().
    In essence, this method activates the client. It spawns two processes.
    One (run_record_and_send() ) is for sending the audio chunk by chunk between 100ms intervals.
    The other (run_receive_and_print) is for handling the incoming responses from the asr server.

    Arguments:
     
     1 argument:  the filename of the wav file. It must be a 16 bit Signed Int PCM file, 44100Hz.

    Flags:
     
     --no-interim: do not send interim results.
    '''

LANG = 'el-GR'
"""string: spoken language to be recognized"""
RATE = 44100
"""int:bitrate of the audio"""
ENC = enums.RecognitionConfig.AudioEncoding.LINEAR16
"""google.cloud.speech.enums.RecognitionConfig.AudioEncoding: audio encoding"""


class ASRClient:

    def run(self,filename,no_interim):
        #main function
        self.client = speech.SpeechClient()
        self.buffer = multiprocessing.Queue()
        p1= multiprocessing.Process(target=self.simulate_record_and_send,args=(filename,self.buffer,))
        p2= multiprocessing.Process(target=self.run_receive_and_print,args=(self.buffer,))
        p1.start()
        p2.start()
        p2.join()
        p1.terminate()

    
    def audio_chunks_from_file_generator(self,filename):
        #this simulates the streaming microphone using an input file

        myaudio = AudioSegment.from_file(filename , "wav") 
        chunk_length_ms = 100 # pydub calculates in millisec
        chunks = make_chunks(myaudio, chunk_length_ms) #Make chunks of one sec

        for i, chunk in enumerate(chunks):
                #print("chunk*")
                time.sleep(0.1)
                yield chunk.raw_data
        
    
    def simulate_record_and_send(self,filename,multiprocessing_buffer):
        # send the audio chunk by chunk between 100ms intervals.

        audio_generator = self.audio_chunks_from_file_generator(filename)
        for chunk in audio_generator:
            multiprocessing_buffer.put(chunk)

    def generate_google_streaming_configuration(self,lang, rate, encoding, single_ut):
        """ Generates a google.cloud.speech.types.StreamingRecognitionConfig object"""

        config = types.RecognitionConfig(
            encoding=encoding,
            sample_rate_hertz=rate,
            language_code=lang,
            audio_channel_count = 2)

        streaming_config = types.StreamingRecognitionConfig(
            config=config,
            interim_results=True,
            single_utterance=single_ut)

        return streaming_config


    def myGenerator(self, q):
        ''' Turns given a given queue into a generator object.

            In other words it takes the buffer and makes a stream out of it.
            It is used to stream incoming audio to Google for transcribing.
            '''
        while True:
            # Use a blocking get() to ensure there's at least one chunk of
            # data, and stop iteration if the chunk is None, indicating the
            # end of the audio stream.
            chunk = q.get()
            if chunk is None:
                return
            data = [chunk]

            # Now consume whatever other data's still buffered.
            while True:
                try:
                    chunk = q.get(block=False)
                    if chunk is None:
                        return
                    data.append(chunk)
                except queue.Empty:
                    break

            yield b''.join(data)


    def run_receive_and_print(self, communication_q):
        ''' Creates and runs the transcription pipeline

        This code is run by a seperate process. Here is where the communication with google 
        takes place. It pipelines the receival of audio, 
        sending it to google, receiving the result and printing it out. This is done by connecting 
        three generators 
        '''

        logging.info("Starting process {}".format(os.getpid()))
        streaming_config = self.generate_google_streaming_configuration(lang=LANG, rate=RATE, encoding=ENC, single_ut=False)

        input_buffer_stream = self.myGenerator(communication_q)
        requests = (types.StreamingRecognizeRequest(audio_content=content)
                    for content in input_buffer_stream)
        responses = self.client.streaming_recognize(streaming_config, requests, timeout=30)
        self.listen_print_loop(responses=responses)

        logging.info("Terminating process {}".format(os.getpid()))



    def listen_print_loop(self, responses):
        """Iterates through Google responses and sends them back to the client.

        Also it sends the SINGLE_UTTERANCE_END signal, which means that google
        does not take into further input, as it is programmed to transcribe 
        only the first utterance of the streamed speech.

        The responses passed is a generator that will block until a response
        is provided by the server.

        Each response may contain multiple results, and each result may contain
        multiple alternatives; for details, see https://goo.gl/tjCPAU.  Here we
        print only the most probable transcript, even if normally we might be 
        given alternatives.

        Finally, responses are provided for interim results as well. If the
        response is an interim one, print a line feed at the end of it, to allow
        the next result to overwrite it, until the response is a final one. For the
        final one, print a newline to preserve the finalized transcription.
        """

        has_stopped_receiving = False
        num_chars_printed = 0
        for response in responses:
            if not response.results:
                if response.speech_event_type:
                    if response.speech_event_type == types.StreamingRecognizeResponse.END_OF_SINGLE_UTTERANCE:
                        has_stopped_receiving = True
                        print("recvd end of single utterance")
                continue

            if response.error:
                if response.error.code != 0:
                    logging.error("Google returned error {}: {}".format(
                        response.error.code, response.error.message))
                    # breaking this loop essentially terminates the process.
                    break

            # The `results` list is consecutive. For streaming, we only care about
            # the first result being considered, since once it's `is_final`, it
            # moves on to considering the next utterance.
            result = response.results[0]
            if not result.alternatives:
                continue

            # Display the transcription of the top alternative.
            transcript = result.alternatives[0].transcript

            # Display interim results, but with a carriage return at the end of the
            # line, so subsequent lines will overwrite them.
            #
            # If the previous result was longer than this one, we need to print
            # some extra spaces to overwrite the previous result
            overwrite_chars = ' ' * (num_chars_printed - len(transcript))

            if not result.is_final:
                sys.stdout.write(transcript + overwrite_chars + '\r')
                sys.stdout.flush()
                print("_INTERIM: " + transcript + overwrite_chars)
                num_chars_printed = len(transcript)

            else:
                logging.info('Got final transcript: "' +
                             transcript + overwrite_chars + '"')
                print(transcript + overwrite_chars)

    

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("filename", type=str, help="source file")
    parser.add_argument("--no-interim",help="Disable display of interim results",action='store_true')
    args=parser.parse_args()
    newClient = ASRClient()
    time.sleep(1)
    newClient.run(args.filename,args.no_interim)
    

if __name__ == '__main__':
    main()
