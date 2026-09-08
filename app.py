import os,json,tempfile,traceback
from pathlib import Path
from fastapi import FastAPI,UploadFile,File,Form
from fastapi.responses import HTMLResponse,JSONResponse
from openai import OpenAI

app=FastAPI(title="Meeting Minutes AI")
ROOT=Path(__file__).parent
DB=ROOT/"meetings.json"
client=OpenAI(api_key=os.environ.get("OPENAI_API_KEY","").strip()) if os.environ.get("OPENAI_API_KEY","").strip() else None

def load():
    try:return json.loads(DB.read_text())
    except:return []
def save(x):DB.write_text(json.dumps(x,ensure_ascii=False,indent=2))

def api_error(message,status=500):
    return JSONResponse({"error":message},status_code=status)

@app.get("/",response_class=HTMLResponse)
def home():return (ROOT/"index.html").read_text()

@app.get("/api/health")
def health():
    return {"ok":True,"ai_configured":client is not None}

@app.get("/api/meetings")
def meetings():return load()

@app.post("/api/meetings")
async def add(payload:dict):
    from datetime import datetime,timezone
    payload["created_at"]=datetime.now(timezone.utc).isoformat()
    x=load();x.insert(0,payload);save(x[:100]);return payload

@app.post("/api/transcribe")
async def transcribe(file:UploadFile=File(...)):
    if not client:return api_error("OPENAI_API_KEY is not configured in Render. Go to Render > Environment and add OPENAI_API_KEY.",503)
    path=None
    try:
        data=await file.read()
        if not data:return api_error("The recording file is empty.",400)
        suffix=Path(file.filename or "meeting.webm").suffix.lower() or ".webm"
        with tempfile.NamedTemporaryFile(delete=False,suffix=suffix) as f:
            f.write(data);path=f.name
        with open(path,"rb") as audio:
            result=client.audio.transcriptions.create(model="gpt-4o-mini-transcribe",file=audio)
        return {"text":getattr(result,"text","")}
    except Exception as e:
        print("TRANSCRIPTION ERROR:",repr(e))
        msg=str(e)
        if "401" in msg or "invalid_api_key" in msg.lower(): msg="OpenAI API key is invalid or expired. Update OPENAI_API_KEY in Render."
        elif "429" in msg: msg="OpenAI API request was rejected or rate limited. Check your API billing/limits and try again."
        elif "model" in msg.lower() and "not found" in msg.lower(): msg="The transcription model is unavailable for this API project."
        return api_error(msg,502)
    finally:
        if path:
            try:os.remove(path)
            except OSError:pass

@app.post("/api/summarize")
async def summarize(transcript:str=Form(...),title:str=Form("Meeting"),attendees:str=Form(""),agenda:str=Form("")):
    if not client:return api_error("OPENAI_API_KEY is not configured in Render. Go to Render > Environment and add OPENAI_API_KEY.",503)
    if not transcript.strip():return api_error("Transcript is empty.",400)
    try:
        prompt="""Create professional meeting minutes. Never invent facts.
Return ONLY JSON with keys: executive_summary, key_points, decisions, action_items, risks_and_issues, open_questions, next_steps.
action_items must contain task, owner, due_date, priority. Use "Not specified" when absent.
Preserve important dates, numbers and commitments.
Title: %s
Attendees: %s
Agenda: %s
Transcript:
%s"""%(title,attendees,agenda,transcript)
        r=client.chat.completions.create(model="gpt-4o-mini",response_format={"type":"json_object"},messages=[{"role":"system","content":"You are an executive meeting secretary."},{"role":"user","content":prompt}],temperature=.2)
        return json.loads(r.choices[0].message.content)
    except Exception as e:
        print("SUMMARY ERROR:",repr(e))
        msg=str(e)
        if "401" in msg or "invalid_api_key" in msg.lower(): msg="OpenAI API key is invalid or expired. Update OPENAI_API_KEY in Render."
        elif "429" in msg: msg="OpenAI API request was rejected or rate limited. Check your API billing/limits and try again."
        return api_error(msg,502)
