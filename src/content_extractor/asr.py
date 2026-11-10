"""Isolated CPU ASR so memory is released before text-model loading."""
import os,sys,json,time
from pathlib import Path
def main():
    os.environ.update(HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',OMP_NUM_THREADS='6',MKL_NUM_THREADS='6')
    def no_network(event,args):
        if event=='socket.connect':raise RuntimeError('Network prohibited during ASR')
    sys.addaudithook(no_network)
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio
    t=time.perf_counter();model=WhisperModel(sys.argv[2],device='cpu',compute_type='int8_float32',cpu_threads=6,num_workers=1,local_files_only=True);load=time.perf_counter()-t
    if model.model.device!='cpu':raise RuntimeError('CPU profile was not respected')
    audio=decode_audio(sys.argv[1],sampling_rate=16000);duration=len(audio)/16000
    if duration>300:raise ValueError('Duration exceeds five minute limit')
    t=time.perf_counter();segments,info=model.transcribe(audio,language=None,beam_size=5,temperature=0,vad_filter=True,condition_on_previous_text=False,initial_prompt=None,word_timestamps=True)
    rows=[];sentences=[];pending=[]
    for s in segments:
        rows.append({'start_ms':round(s.start*1000),'end_ms':round(s.end*1000),'text':s.text.strip()})
        for w in s.words or []:
            pending.append(w)
            if w.word.rstrip().endswith(('.','?','!')) or len(pending)>=100:
                sentences.append({'start_ms':round(pending[0].start*1000),'end_ms':round(pending[-1].end*1000),'text':''.join(x.word for x in pending).strip()});pending=[]
    if pending:sentences.append({'start_ms':round(pending[0].start*1000),'end_ms':round(pending[-1].end*1000),'text':''.join(x.word for x in pending).strip()})
    Path(sys.argv[3]).write_text(json.dumps({'duration_ms':round(duration*1000),'language':info.language,'segments':rows,'sentences':sentences,'load_seconds':load,'asr_seconds':time.perf_counter()-t}),encoding='utf-8')
if __name__=='__main__':main()
