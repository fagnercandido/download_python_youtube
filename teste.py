import whisper

model = whisper.load_model("large")
result = model.transcribe("aula4.mp4", fp16=False)
print(result['text'])
