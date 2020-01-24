
# transcribe_file_with_google_asr.py

""" Simple script for ASR with google, takes as input a wav file
    (specs:  ....)
    Make sure that $GOOGLE_APPLICATION_CREDENTIALS is set to 
    the credentials file.

"""

from google.cloud import speech
from google.cloud.speech import enums
from google.cloud.speech import types
import argparse
import google

LANG = 'el-GR'
"""string: spoken language to be recognized"""
RATE = 44100
"""int:bitrate of the audio"""
ENC = enums.RecognitionConfig.AudioEncoding.LINEAR16
"""google.cloud.speech.enums.RecognitionConfig.AudioEncoding: audio encoding"""

def generate_google_configuration(lang, rate, encoding):
    """ Generates a google.cloud.speech.types.RecognitionConfig object"""
    config = types.RecognitionConfig(
        encoding=encoding,
        language_code=lang,
        audio_channel_count = 2)
    return config


def transcribe_file(filename):

    client = speech.SpeechClient()
    config = generate_google_configuration(LANG,RATE,ENC)
    with open(filename,'rb') as audiofile:
        audio = types.RecognitionAudio(content=audiofile.read())

    audio = {"uri": "gs://test-bucket-mystery/out3.wav"}

    
    operation = client.long_running_recognize(config, audio)

    print(u"Waiting for operation to complete...")
    response = operation.result()

    for result in response.results:
        # First alternative is the most probable result
        alternative = result.alternatives[0]
        print(u"Transcript: {}".format(alternative.transcript))



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("filename", type=str, help="source file")
    args = parser.parse_args()
    transcribe_file(args.filename)

if __name__ == '__main__':
    main()
          
