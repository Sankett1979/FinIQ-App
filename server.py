from flask import Flask, request, jsonify, send_file
import os
import io
import pandas as pd
import PyPDF2
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone

# Import our Brain
from semantic_engine import SemanticEngine

app = Flask(__name__)
brain = SemanticEngine()
DB_URL = os.environ.get("DATABASE_URL", "postgresql://postgres.your_project_ref:YOUR_PASSWORD@aws-0-your-region.pooler.supabase.com:6543/postgres")

def get_db():
    return psycopg2.connect(DB_URL)

@app.route('/')
def index():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(base_dir, 'FINIQ_Prototype.html')
    return send_file(html_path)

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').lower()
    password = data.get('password', '')
    
    # HARDCODED DEMO ACCOUNTS FOR PITCH
    if username == 'analyst':
        return jsonify({"status": "success", "user": {"username": "analyst", "name": "Sarah Jenkins", "role": "Data Analyst"}})
    if username == 'executive':
        return jsonify({"status": "success", "user": {"username": "executive", "name": "Michael Chang", "role": "Chief Financial Officer"}})
    if username == 'guest':
        return jsonify({"status": "success", "user": {"username": "guest", "name": "Guest User", "role": "Read-Only"}})
        
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE username = %s AND password_hash = %s", (username, password))
    user = cur.fetchone()
    cur.close()
    conn.close()
    
    if user:
        return jsonify({"status": "success", "user": user})
    else:
        return jsonify({"status": "error", "message": "Invalid username or password"}), 401

@app.route('/api/sessions', methods=['GET'])
def get_sessions():
    user_id = request.args.get('user_id')
    if user_id == 'guest':
        return jsonify([]) # Guest has no history
        
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Auto-delete old chats
    cur.execute("DELETE FROM chat_sessions WHERE is_pinned = FALSE AND created_at < NOW() - INTERVAL '7 days'")
    cur.execute("DELETE FROM chat_sessions WHERE is_pinned = TRUE AND created_at < NOW() - INTERVAL '30 days'")
    conn.commit()
    
    if user_id:
        cur.execute("SELECT session_id, title, is_pinned, created_at FROM chat_sessions WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
    else:
        cur.execute("SELECT session_id, title, is_pinned, created_at FROM chat_sessions ORDER BY created_at DESC")
    sessions = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(sessions)

@app.route('/api/sessions/<session_id>/messages', methods=['GET'])
def get_messages(session_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT role, content, created_at FROM chat_messages WHERE session_id = %s ORDER BY created_at ASC", (session_id,))
    messages = cur.fetchall()
    cur.close()
    conn.close()
    for m in messages:
        if m.get('created_at'):
            m['created_at'] = m['created_at'].isoformat()
    return jsonify(messages)

@app.route('/api/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM chat_sessions WHERE session_id = %s", (session_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/api/sessions/<session_id>/pin', methods=['POST'])
def toggle_pin(session_id):
    data = request.json
    is_pinned = data.get('is_pinned', True)
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    if not is_pinned:
        # Check age logic
        cur.execute("SELECT created_at FROM chat_sessions WHERE session_id = %s", (session_id,))
        session = cur.fetchone()
        if session and session['created_at']:
            age_days = (datetime.now(timezone.utc) - session['created_at']).days
            if age_days >= 7:
                # Delete instead of unpin
                cur.execute("DELETE FROM chat_sessions WHERE session_id = %s", (session_id,))
                conn.commit()
                cur.close()
                conn.close()
                return jsonify({"status": "deleted", "reason": "older_than_7_days"})
    
    # Otherwise, update normally
    cur.execute("UPDATE chat_sessions SET is_pinned = %s WHERE session_id = %s", (is_pinned, session_id))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "success", "is_pinned": is_pinned})

@app.route('/api/sessions/<session_id>/rename', methods=['POST'])
def rename_session(session_id):
    data = request.json
    new_title = data.get('title')
    if new_title:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE chat_sessions SET title = %s WHERE session_id = %s", (new_title, session_id))
        conn.commit()
        cur.close()
        conn.close()
    return jsonify({"status": "success"})



@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400
        
    user_id = request.form.get('user_id', 'unknown')
    
    filename = file.filename
    ext = filename.split('.')[-1].lower()
    
    extracted_text = ""
    
    try:
        if ext == 'pdf':
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text = page.extract_text()
                if text:
                    extracted_text += text + "\n"
        elif ext in ['xlsx', 'csv']:
            if ext == 'csv':
                df = pd.read_csv(file)
                extracted_text = df.to_csv(index=False)
            else:
                dfs = pd.read_excel(file, sheet_name=None)
                for sheet_name, df in dfs.items():
                    extracted_text += f"\n--- SHEET: {sheet_name} ---\n"
                    extracted_text += df.to_csv(index=False) + "\n"
        else:
            return jsonify({"status": "error", "message": "Unsupported file type"}), 400
            
        if not extracted_text.strip():
            return jsonify({"status": "error", "message": "Could not extract text from file"}), 400
            
        # Save to database
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO finiq_external_docs (filename, doc_type, extracted_text, uploaded_by) VALUES (%s, %s, %s, %s)",
            (filename, ext, extracted_text, user_id)
        )
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({"status": "success", "message": f"Successfully ingested {filename}"})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/documents', methods=['GET'])
def get_documents():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT doc_id, filename, doc_type, uploaded_by, uploaded_at FROM finiq_external_docs ORDER BY uploaded_at DESC")
    docs = cur.fetchall()
    cur.close()
    conn.close()
    
    # format dates
    for d in docs:
        if d.get('uploaded_at'):
            d['uploaded_at'] = d['uploaded_at'].isoformat()
            
    return jsonify(docs)


@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    query = data.get('query', '')
    session_id = data.get('session_id', None)
    user_id = data.get('user_id', None)
    
    # 0. Fetch history from DB if session_id exists
    history = data.get('history', [])
    if session_id and not history:
        try:
            conn = get_db()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT role, content FROM chat_messages WHERE session_id = %s ORDER BY created_at ASC", (session_id,))
            history = cur.fetchall()
            conn.close()
        except Exception as e:
            print("Failed to fetch history:", e)
            pass

    # 1. Ask Brain FIRST (so we don't save DB if it crashes)
    result = brain.ask(query, history)
    
    # Fallback to current time if we don't save to DB
    user_timestamp = datetime.now(timezone.utc).isoformat()
    ai_timestamp = datetime.now(timezone.utc).isoformat()
    
    if user_id != 'guest' and user_id is not None:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        if not session_id:
            session_id = str(uuid.uuid4())
            title = query[:30] + '...' if len(query) > 30 else query
            cur.execute("INSERT INTO chat_sessions (session_id, title, user_id) VALUES (%s, %s, %s)", (session_id, title, user_id))
            conn.commit()
        
        cur.execute("INSERT INTO chat_messages (session_id, role, content) VALUES (%s, %s, %s) RETURNING created_at", (session_id, 'user', query))
        user_timestamp = cur.fetchone()['created_at'].isoformat()
        
        ai_content = result.get('narrative', 'Error generating response')
        cur.execute("INSERT INTO chat_messages (session_id, role, content) VALUES (%s, %s, %s) RETURNING created_at", (session_id, 'ai', ai_content))
        ai_timestamp = cur.fetchone()['created_at'].isoformat()
        
        conn.commit()
        cur.close()
        conn.close()
    
    result['session_id'] = session_id
    result['user_timestamp'] = user_timestamp
    result['ai_timestamp'] = ai_timestamp
    return jsonify(result)

if __name__ == '__main__':
    print("FINIQ Enterprise Dashboard is LIVE at http://127.0.0.1:8080")
    app.run(host='127.0.0.1', port=8080, debug=False)
