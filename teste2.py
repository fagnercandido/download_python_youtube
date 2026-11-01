import os
import speech_recognition as sr

#command2mp3 = 'ffmpeg -i aula4.mp4 aula4.mp3'
#command2wav = 'ffmpeg -i aula4.mp3 aula4.wav'

#os.system(command2mp3)
#os.system(command2wav)

r = sr.Recognizer()
with sr.AudioFile('aula4.wav') as source:
    audio = r.record(source)

print('Começando')
print(r.recognize_google(audio))
print('Fim')