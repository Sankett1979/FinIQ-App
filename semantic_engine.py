import json
import os
from sqlalchemy import create_engine, text
# AI Clients imported dynamically
import re
import time

class SemanticEngine:
    def __init__(self):
        # Supabase Cloud SQL Connection from environment variable
        self.db_url = os.environ.get("DATABASE_URL", "postgresql://postgres.your_project_ref:YOUR_PASSWORD@aws-0-your-region.pooler.supabase.com:6543/postgres")
        self.engine = create_engine(self.db_url)

        # AI Provider Auto-Detection (OpenAI or Google Gemini)
        openai_key = os.environ.get("OPENAI_API_KEY")
        gemini_key = os.environ.get("GEMINI_API_KEY")

        if openai_key or (gemini_key and gemini_key.strip().startswith("sk-")):
            from openai import OpenAI
            key = (openai_key or gemini_key).strip()
            self.openai_client = OpenAI(api_key=key)
            self.openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            self.provider = "openai"
            print(f"[SemanticEngine] Initialized with OpenAI ({self.openai_model})")
        else:
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=gemini_key or "YOUR_GEMINI_API_KEY")
                self.provider = "gemini"
                print("[SemanticEngine] Initialized with Google Gemini")
            except Exception as e:
                from openai import OpenAI
                self.openai_client = OpenAI(api_key=openai_key or gemini_key or "YOUR_OPENAI_KEY")
                self.openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
                self.provider = "openai" 

    def _call_llm(self, prompt):
        if self.provider == "openai":
            resp = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0
            )
            return resp.choices[0].message.content or ""
        else:
            resp = self.gemini_client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt
            )
            return resp.text or ""

    def _fetch_live_news(self):
        import urllib.request
        import xml.etree.ElementTree as ET
        
        # Using Google News Finance Search and Yahoo Finance (Highly reliable live feeds for Sept 2026)
        sources = [
            ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
            ("Google Finance News", "https://news.google.com/rss/search?q=finance+OR+banking+when:1d&hl=en-US&gl=US&ceid=US:en")
        ]
        
        articles = []
        for source_name, url in sources:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=4) as response:
                    root = ET.fromstring(response.read())
                    for item in root.findall('.//item')[:5]:
                        title = item.find('title').text
                        link = item.find('link').text
                        
                        # Clean up Google News titles (removes the " - Source Name" at the end)
                        if " - " in title and source_name == "Google Finance News":
                            title = title.rsplit(" - ", 1)[0]
                            
                        # Generate dynamic 2-3 word header
                        t_lower = title.lower()
                        if 'bank' in t_lower or 'loan' in t_lower or 'fed ' in t_lower: cat = 'Banking & Finance'
                        elif 'stock' in t_lower or 'market' in t_lower or 'share' in t_lower: cat = 'Market Trends'
                        elif 'rate' in t_lower or 'inflation' in t_lower or 'economy' in t_lower: cat = 'Global Economy'
                        elif 'deal' in t_lower or 'buy' in t_lower or 'acquire' in t_lower: cat = 'M&A Activity'
                        elif 'tech' in t_lower or 'ai ' in t_lower or 'crypto' in t_lower: cat = 'Technology Sector'
                        else:
                            cat = " ".join(title.split()[:2]).replace(':', '') + " Update"
                            
                        articles.append({'source': source_name, 'title': title, 'link': link, 'category': cat})
            except Exception as e:
                pass
                
        selected = articles[:5]
        if not selected:
            return "📰 **Market & Financial Updates**<br><br>Unable to fetch live news at the moment."
            
        html = "📰 **Market & Financial Updates (Last 24h)**<br><br>"
        for i, art in enumerate(selected, 1):
            html += f"{i}. **{art['category']}:** <a href='{art['link']}' target='_blank' style='color:#2563a8; text-decoration:underline;'>{art['title']}</a><br><br>"
        return html

    def ask(self, query, history=None):
        print(f"\\n[AI Processing]: '{query}'")

        # -----------------------------------------------------
        # STATIC SLASH COMMAND INTERCEPTORS FOR DEMO
        # -----------------------------------------------------
        q_lower = query.strip().lower()
        q_clean = q_lower.replace('?', '').replace('.', '').strip()
        
        # Scenario 1: Revenue Drill-Down
        if q_clean == "what was my pbt in comparison to july":
            return {
                "platform": "FINIQ Static",
                "narrative": "Profit Before Tax (PBT) for August 2026 was **$65,730M**, which is **down $4,120M (-5.9%)** compared to July 2026.<br><br>This decline was primarily driven by a sharp drop in **Gross Revenue**, which completely offset our slight improvements in operating expenses.",
                "sql_executed": "SELECT Metric, Month, Value_Millions FROM mit_pnl WHERE Metric ILIKE '%INCOME BEFORE INCOME TAXES%' AND Month IN ('2026-07', '2026-08');"
            }
        elif q_clean == "which product is causing lower revenue versus july":
            return {
                "platform": "FINIQ Static",
                "narrative": "The decline in revenue is heavily concentrated in our **Global Markets - FX Derivatives** product line.<br><br>FX Derivatives revenue fell by **$3,850M** month-over-month, accounting for 93% of the total revenue shortfall.",
                "sql_executed": "SELECT Product_Line, SUM(Amount_USD) as Revenue_Drop FROM dmi_unified_ledger WHERE Record_Type='Actual' AND Month='2026-08' GROUP BY Product_Line ORDER BY Revenue_Drop ASC LIMIT 1;"
            }
        elif q_clean == "which rm":
            return {
                "platform": "FINIQ Static",
                "narrative": "Analysis of the FX Derivatives portfolio shows the shortfall is tied to the APAC institutional desk.<br><br>The primary Relationship Manager (RM) overseeing this segment is **Michael Chang (Managing Director, APAC FX)**, whose key client accounts saw severely reduced trading volumes in August.",
                "sql_executed": "SELECT Relationship_Manager, SUM(Amount_USD) as Revenue_Drop FROM dmi_unified_ledger WHERE Product_Line='FX Derivatives' AND Month='2026-08' GROUP BY Relationship_Manager ORDER BY Revenue_Drop ASC LIMIT 1;"
            }
        # Scenario 2: OPEX Drill-Down
        elif q_clean == "what was my cost versus july month":
            return {
                "platform": "FINIQ Static",
                "narrative": "Total Operating Expenses (OPEX) for August 2026 were **$12,450M**, representing a favorable decrease of **$320M (-2.5%)** compared to July 2026.",
                "sql_executed": "SELECT Month, SUM(Expense_Amount_USD) FROM opex_transactions WHERE Month IN ('2026-07', '2026-08') GROUP BY Month;"
            }
        elif q_clean == "which cost centers spent less":
            return {
                "platform": "FINIQ Static",
                "narrative": "The $320M reduction in OPEX was primarily driven by underspend in three key cost centers:<br><br><ul><li>**CC-8921 (Global Marketing):** -$150M</li><li>**CC-4410 (APAC IT Infrastructure):** -$110M</li><li>**CC-1190 (EMEA Legal):** -$60M</li></ul>",
                "sql_executed": "SELECT Cost_Center_Code, Variance_USD FROM opex_transactions WHERE Month='2026-08' ORDER BY Variance_USD ASC LIMIT 3;"
            }
        elif q_clean == "who are the cost center owners":
            return {
                "platform": "FINIQ Static",
                "narrative": "Here are the accountable owners for those underspent cost centers:<br><br><ul><li>**CC-8921 (Global Marketing):** Sarah Jenkins</li><li>**CC-4410 (APAC IT):** David Chen</li><li>**CC-1190 (EMEA Legal):** Robert Wellington</li></ul>",
                "sql_executed": "SELECT Cost_Center_Code, Cost_Center_Owner FROM dmi_cost_centers WHERE Cost_Center_Code IN ('CC-8921', 'CC-4410', 'CC-1190');"
            }
            
        elif q_clean in ["suggest next steps", "what are the next steps", "what should we do"]:
            # Check history to determine which scenario we are in
            is_opex = False
            if history:
                last_user_msgs = [m.get('content', '').lower() for m in history if m.get('role') == 'user']
                if last_user_msgs:
                    last_msg = last_user_msgs[-1]
                    if 'cost' in last_msg or 'opex' in last_msg or 'owner' in last_msg:
                        is_opex = True
            
            if is_opex:
                return {
                    "platform": "FINIQ Static",
                    "narrative": "Would you like to check with the cost center owners if the rolling forecast needs to be updated?",
                    "sql_executed": "N/A"
                }
            else:
                return {
                    "platform": "FINIQ Static",
                    "narrative": "Would you like me to automatically draft an email to Michael Chang and the APAC Head of Markets to schedule a strategic review?",
                    "sql_executed": "N/A"
                }
            
        if q_lower == "/morning brief":
            return {
                "platform": "FINIQ Static",
                "narrative": "Good morning! Here is your daily executive brief:<br><br>"
                             "🔹 **Upcoming Meetings:**<br>"
                             "🔸 09:00 AM - Q3 Strategy Alignment with Global Heads<br>"
                             "🔸 11:30 AM - Board Review: APAC Expansion<br>"
                             "🔸 02:00 PM - 1:1 with Chief Risk Officer<br><br>"
                             "🔹 **Flash Results (YTD):**<br>"
                             "PBT is tracking strong at $278.5B, driven by $310.2B in Revenue, offset by $125.4B in Operating Expenses.<br><br>"
                             "🔹 **Share Price:**<br>"
                             "ApexFin Corp (APX) closed at **$142.50 (+1.2%)** on Friday, outperforming the broader financial index."
            }
        elif q_lower == "/flash report" or q_lower == "/flash":
            return {
                "platform": "FINIQ Static",
                "narrative": "⚡ **FINANCIAL FLASH REPORT (YTD vs TARGET)** ⚡<br><br>"
                             "🔹 **PBT:** $278.5B Actual vs $250.0B Target (🟢 +11.4% Favorable)<br>"
                             "🔹 **Revenue:** $310.2B Actual vs $295.0B Target (🟢 +5.1% Favorable)<br>"
                             "🔹 **Operating Expenses:** $125.4B Actual vs $120.0B Target (🔴 -4.5% Adverse)<br>"
                             "🔹 **ECLs (Expected Credit Losses):** $12.1B Actual vs $15.0B Target (🟢 +19.3% Favorable)"
            }
        elif q_lower == "/news":
            return {
                "platform": "Live RSS Feed (Yahoo & Google News)",
                "narrative": self._fetch_live_news()
            }

        if history is None:
            history = []

        history_text = ""
        for msg in history[-4:]:
            role = "User" if msg.get("role") == "user" else "FINIQ"
            history_text += f"{role}: {msg.get('content')}\\n"

        system_prompt_base = f"""You are FINIQ, an Enterprise Finance AI.
Your ONLY data source is the centralized Supabase PostgreSQL Data Warehouse.
The schema contains these 6 tables:
1. opex_transactions (Date, Transaction_ID, Cost_Center_Code, Expense_Code, Expense_Amount_USD)
2. dmi_unified_ledger (Date, Transaction_ID, Cost_Center_Code, Product_ID, Segment_ID, Revenue_Code, Revenue_Amount_USD)
3. hr_workforce_roster (Employee_ID, First_Name, Last_Name, Corporate_Email, Worker_Type, Region, Country, City_Location, Legal_Entity, Business_Segment, Cost_Center_Code, Job_Title, Corporate_Title, FTE_Factor, Local_Currency, Annual_Base_Salary_Local, Annual_Base_Salary_USD_Eq, Original_Hire_Date, Status)
4. mit_pnl (Metric, Month, Value_Millions)
5. dmi_cost_centers (Cost_Center_Code, Cost_Center_Short, Cost_Center_Long, Legal_Entity, CC_Category, Business_Segment, Region, Cost_Center_Owner)
6. finiq_external_docs (doc_id, filename, doc_type, extracted_text, uploaded_by, uploaded_at)

CRITICAL SEMANTIC MAPPINGS:
- If the user asks for "Profit Before Tax" or "PBT", query for "%INCOME BEFORE INCOME TAXES%" in the Metric column (using ILIKE because it usually has (Actual) or (Forecast) appended).
- If the user asks for "Current Month" or "This Month", use Month = '2026-08' (August 2026 is the last closed actuals month).

CONVERSATION HISTORY:
{history_text}
"""

        dynamic_prompt = system_prompt_base + f"""
USER QUERY: {query}

INSTRUCTIONS FOR ROUTING:
- You must decide how to handle this query.
- CRITICAL: PostgreSQL is case-sensitive for these tables. You MUST wrap ALL column names in double quotes. BECAUSE YOU ARE RETURNING JSON, YOU MUST ESCAPE THOSE QUOTES: e.g. {{"action": "sql", "sql_query": "SELECT \"Country\" FROM hr_workforce_roster"}}
- To find the owner or manager of a cost center, JOIN with the dmi_cost_centers table using "Cost_Center_Code".
- IMPORTANT EXTERNAL RAG: If the user asks about an external competitor, PDF, or Excel upload, query the finiq_external_docs table. Do NOT filter by filename if comparing multiple companies. Example: SELECT \"filename\", \"extracted_text\" FROM finiq_external_docs; The massive extracted_text will be returned to you in step 2 so you can cross-reference it.
- Reply EXACTLY with a JSON object. No markdown, no conversational text.
- If the question can be answered by SQL, return: {{"action": "sql", "sql_query": "SELECT ..."}}
- If the question cannot be answered by SQL, return: {{"action": "reply", "message": "I cannot answer this."}}
"""

        max_retries = 3
        plan = {"action": "reply", "message": "Failed to parse"}
        
        for attempt in range(max_retries):
            try:
                raw_plan = self._call_llm(dynamic_prompt)
                plan = self.extract_json(raw_plan)
                print(f" -> [LLM Route Plan Attempt {attempt+1}]:", plan)
                break
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    return {"error": "API Rate Limit Exceeded. Please wait 30-60 seconds."}
                if attempt == max_retries - 1:
                    return {"error": f"LLM Routing Error (Network/DNS): {error_str}"}
                time.sleep(1)

        if plan.get("action") == "reply":
            return {
                "platform": "Error Handler",
                "narrative": plan.get("message", "I am unable to process this request."),
                "sql_executed": "N/A"
            }
            
        sql_query = plan.get("sql_query", "")
        data = []
        platform = "Supabase Cloud Data Warehouse"

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(sql_query))
                data = [dict(row._mapping) for row in result]
        except Exception as e:
            return {
                "platform": platform,
                "error": f"Database Execution Error: {str(e)}",
                "sql_executed": sql_query
            }

        narrative_prompt = f"""You are FINIQ, an Enterprise Finance AI.
User Query: {query}
SQL Executed: {sql_query}
Raw Data Returned: {str(data)[:400000]}

INSTRUCTIONS:
1. Start directly with the answer summarizing the main result. Do NOT use conversational filler like "I accessed the database" or "Here is the data". Be direct, professional, and executive-level.
2. Present the actual data, drivers, or answers as concise bullet points, UNLESS the user explicitly requests a table or tabular form.
3. If Raw Data is empty ([]), clearly state that no records were found after thorough database verification.
4. Keep the overall response brief and punchy. Do not hallucinate.
5. CRITICAL MARKDOWN RULE: Never use the tilde symbol (~) to mean "approximately" as it breaks markdown strikethrough rendering. Always use "approx." or "c." instead.
"""

        for attempt in range(max_retries):
            try:
                narrative = self._call_llm(narrative_prompt)
                break
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    return {"error": "API Rate Limit Exceeded. The free-tier API key allows ~15 requests per minute.", "platform": platform}
                if attempt == max_retries - 1:
                    return {"error": f"LLM Narrative Error (Network/DNS): {error_str}", "platform": platform}
                time.sleep(1)

        return {
            "platform": platform,
            "data": {"Status": "Data successfully processed"},
            "narrative": narrative,
            "sql_executed": sql_query
        }

    def extract_json(self, text_resp):
        import json
        import re
        text_resp = text_resp.strip()
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text_resp, re.DOTALL | re.IGNORECASE)
        if match:
            text_resp = match.group(1)
        else:
            start = text_resp.find('{')
            end = text_resp.rfind('}')
            if start != -1 and end != -1:
                text_resp = text_resp[start:end+1]
        try:
            return json.loads(text_resp)
        except Exception as e:
            print("JSON parse error:", e)
            raise ValueError("Invalid JSON generated by LLM")
