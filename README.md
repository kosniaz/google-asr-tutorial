# google-asr-tutorial
A quick-and-dirty tutorial on using google-cloud speech-to-text and python.


## Introduction

Python's cloud.speech module includes three methods for ASR:

* [recognize(config,audio)](https://cloud.google.com/speech-to-text/docs/sync-recognize)
* [long_running_recognize(config, audio)](https://cloud.google.com/speech-to-text/docs/async-recognize)
* [streaming_recognize(streaming_config, requests)](https://cloud.google.com/speech-to-text/docs/streaming-recognize)

Each of these is documented in Google Cloud's website. However, the documentation is not thorough. For example, there is no list of the possible errors that may be encountered, and some parts of the docs are outdated. This repo aspires to clear some of the confusion caused by the ambiguous docs lying around in google's websites.


## Streaming recognition: the most complicated case



### Step 1: understanding Generators 

Disclaimer: the examples are taken from [this](https://www.programiz.com/python-programming/generator) tutorial.

A Generator is a bit like an iterator. It is similar, in a way, to the idea of lazy evaluation done by languages like Haskell. It is like a list whose next element is generated on the fly. A generator is defined much like a function:

```
def my_gen():
    n = 1
    print('This is printed first')
    # Generator function contains yield statements
    yield n

    n += 1
    print('This is printed second')
    yield n

    n += 1
    print('This is printed at last')
    yield n
```
Note that the generator is defined exactly like a function, but instead of one return value, it has one or more *yielded values*. Given a generator object `a`, one can call
` a.next()` to get the next item on the list. However, a much more popular way to use a generator would be like this:

```
# Using for loop
a = my_gen()
for item in a:
    print(item)    
```
### Step 1b: understanding Generator *Expressions*

(https://www.programiz.com/python-programming/generator#expression)

### Step 2: understanding generator pipelines
(https://www.programiz.com/python-programming/generator#use)

### Step 3: using all the above steps to create a script that performs streaming recognition.

(https://cloud.google.com/speech-to-text/docs/streaming-recognize#performing_streaming_speech_recognition_on_an_audio_stream)

## The problem of transcribing a (relatively) long speech track

### Method 1: Using long-running recognition

This is the method that is used for longer tracks. There seem to be no problem with long pauses within the text too, which is a plus in relation with method 2. However, the catch here is that files greater than 10MB must be uploaded to the Google cloud before being processed. 

### Method 2: Using streaming recognition (without END-OF-SINGLE-UTTERANCE)

This method might achieve better results than the previous one, however:

* Audio should be more-or-less continuous. No long pauses allowed, or we have 
```
Google returned error 11: Audio Timeout Error: Long duration elapsed without audio. Audio should be sent close to real time.
```
* limited time available (up to x minutes, after we get an error)
```
google.api_core.exceptions.DeadlineExceeded: 504 Deadline Exceeded
```
