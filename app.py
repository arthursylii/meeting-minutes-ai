import os,json,tempfile
from pathlib import Path
from fastapi import FastAPI,UploadFile,File,Form
from fastapi.responses import HTMLResponse,JSONResponse
from openai import OpenAI
app=FastAPI(title='Meeting Minutes AI')
ROOT=Path(__file__).parent;DB=ROOT/'meetings.json'
client=OpenAI(api_key=os.environ['OPENAI_API_KEY']) if os.environ.get('OPENAI_API_KEY') else None
def load():
    try:return json.loads(DB.read_text())
    except:return []
def save(x):DB.write_text(json.dumps(x,ensure_ascii=False,indent=2))
@app.get('/',response_class=HTMLResponse)
def home():return (ROOT/'index.html').read_text()
@app.get('/api/health')
def health():return {'ok':True,'ai_configured':client is not None}
@app.get('/api/meetings')
def meetings():return load()
@app.post('/api/meetings')
async def add(payload:dict):
    from datetime import datetime,timezone
    payload['created_at']=datetime.now(timezone.utc).isoformat();x=load();x.insert(0,payload);save(x[:100]);return payload
@app.post('/api/transcribe')
async def transcribe(file:UploadFile=File(...)):
    if not client:return JSONResponse({'error':'OPENAI_API_KEY is not configured.'},status_code=503)
    suffix=Path(file.filename or 'meeting.webm').suffix or '.webm'
    with tempfile.NamedTemporaryFile(delete=False,suffix=suffix) as f:f.write(await file.read());path=f.name
    try:
        with open(path,'rb') as a:r=client.audio.transcriptions.create(model='gpt-4o-mini-transcribe',file=a)
        return {'text':r.text}
    finally:
        try:os.remove(path)
        except OSError:pass
@app.post('/api/summarize')
async def summarize(transcript:str=Form(...),title:str=Form('Meeting'),attendees:str=Form(''),agenda:str=Form('')):
    if not client:return JSONResponse({'error':'OPENAI_API_KEY is not configured.'},status_code=503)
    prompt='Create professional meeting minutes. Never invent facts. Return ONLY JSON with keys executive_summary, key_points, decisions, action_items, risks_and_issues, open_questions, next_steps. action_items must contain task, owner, due_date, priority. Use Not specified when absent. Preserve important dates, numbers and commitments. Title: '+title+' Attendees: '+attendees+' Agenda: '+agenda+' Transcript: '+transcript
    r=client.chat.completions.create(model='gpt-4o-mini',response_format={'type':'json_object'},messages=[{'role':'system','content':'You are an executive meeting secretary.'},{'role':'user','content':prompt}],temperature=.2)
    return json.loads(r.choices[0].message.content)
