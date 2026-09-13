import os
import json
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
import smtplib
import html
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# ============================================================
# 1. FETCH NEWS
# ============================================================

queries = [
    "India government policy",
    "India economy RBI",
    "Supreme Court India",
    "India environment climate",
    "India science technology",
    "India international relations",
    "India government schemes"
]

articles = []

for query in queries:

    encoded_query = urllib.parse.quote(query)

    rss_url = (
        "https://news.google.com/rss/search?"
        f"q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    try:

        with urllib.request.urlopen(rss_url, timeout=20) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)

        for item in root.findall(".//item")[:5]:

            title = item.findtext("title", "")
            link = item.findtext("link", "")
            description = item.findtext("description", "")

            articles.append({
                "title": title,
                "link": link,
                "description": description
            })

    except Exception as e:
        print(f"Could not fetch '{query}': {e}")


# ============================================================
# 2. REMOVE DUPLICATES
# ============================================================

unique_articles = {}

for article in articles:

    title = article["title"].strip()

    if title:
        unique_articles[title] = article

articles = list(unique_articles.values())

print(f"Collected {len(articles)} unique articles.")

if not articles:
    raise Exception("No news articles were collected.")


# ============================================================
# 3. PREPARE NEWS FOR GEMINI
# ============================================================

news_text = ""

for i, article in enumerate(articles[:30], 1):

    news_text += (
        f"\nARTICLE {i}\n"
        f"TITLE: {article['title']}\n"
        f"DESCRIPTION: {article['description']}\n"
        f"SOURCE LINK: {article['link']}\n"
        f"--------------------------------------------------\n"
    )


# ============================================================
# 4. GEMINI PROMPT
# ============================================================

prompt = f"""
You are an expert UPSC Civil Services Examination
current-affairs analyst.

Create a concise daily UPSC current-affairs briefing
from the supplied news articles.

IMPORTANT:

Do not invent facts.

Do not claim that a government action happened unless
the supplied article supports it.

Do not create statistics, dates, laws, schemes or
organizations that are not supported by the supplied
material.

If something is uncertain, clearly say it requires
verification.

PRIORITIZE:

- Indian Polity
- Constitution
- Governance
- Judiciary
- Government schemes
- Economy
- Banking and RBI
- Environment
- Climate change
- Biodiversity
- Agriculture
- Science and Technology
- International Relations
- Internal Security
- Social Issues
- Important reports and indices

IGNORE:

- Sports
- Entertainment
- Celebrity news
- Gossip
- Advertisements
- Trivial local news
- Sensational stories with little UPSC relevance

Select approximately 5-8 important topics.

For every selected topic provide:

TITLE

CATEGORY

UPSC RELEVANCE SCORE: X/100

WHAT HAPPENED:
Explain in 2-4 sentences.

WHY IT MATTERS FOR UPSC:
Explain in 2-4 sentences.

GS PAPER:
GS-1, GS-2, GS-3, GS-4 or Essay.

PRELIMS FACTS:
Exactly 3 useful facts.

MAINS ANGLE:
One analytical Mains question.

SOURCE:
Article title and source link.

At the end provide:

TOP 5 QUICK REVISION POINTS

Then provide:

3 PRELIMS MCQs

Each MCQ must contain:

Question
A-D options
Correct answer
One-line explanation

Finally provide:

1 MAINS PRACTICE QUESTION

NEWS ARTICLES:

{news_text}
"""


# ============================================================
# 5. CALL GEMINI
# ============================================================

api_key = os.environ["GEMINI_API_KEY"]

gemini_url = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-3.5-flash:generateContent"
)

request_body = {
    "contents": [
        {
            "parts": [
                {
                    "text": prompt
                }
            ]
        }
    ]
}

request = urllib.request.Request(
    gemini_url,
    data=json.dumps(request_body).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    },
    method="POST"
)

try:

    with urllib.request.urlopen(
        request,
        timeout=120
    ) as response:

        result = json.loads(
            response.read().decode("utf-8")
        )

except urllib.error.HTTPError as e:

    print(f"Gemini API returned HTTP {e.code}")
    print(e.read().decode("utf-8"))
    raise


# ============================================================
# 6. EXTRACT RESPONSE
# ============================================================

try:

    briefing = (
        result["candidates"][0]
        ["content"]["parts"][0]["text"]
    )

except Exception:

    print("Unexpected Gemini response:")
    print(json.dumps(result, indent=2))
    raise


print("\n====================================")
print("UPSC DAILY CURRENT AFFAIRS")
print("====================================\n")

print(briefing)


# ============================================================
# 7. CREATE BEAUTIFUL HTML EMAIL
# ============================================================

from datetime import datetime

today = datetime.now().strftime("%d %B %Y")


def inline_format(text):
    text = html.escape(text)

    # Remove escaped markdown characters
    text = text.replace(r"\*", "*")
    text = text.replace(r"\_", "_")

    # Bold markdown
    import re
    text = re.sub(
        r"\*\*(.*?)\*\*",
        r"<strong>\1</strong>",
        text
    )

    # Markdown links
    text = re.sub(
        r"\[(.*?)\]\\?\((https?://.*?)\)",
        r'<a href="\2" target="_blank">\1</a>',
        text
    )

    # Plain URLs
    text = re.sub(
        r'(?<!["=])(https?://[^\s<]+)',
        r'<a href="\1" target="_blank">Read Source</a>',
        text
    )

    return text


def build_html(briefing):

    lines = briefing.replace("\r", "").split("\n")

    output = []

    topic_open = False
    list_open = False

    for raw_line in lines:

        line = raw_line.strip()

        if not line:
            if list_open:
                output.append("</ol>")
                list_open = False

            continue

        # -----------------------------------------
        # TOPIC
        # -----------------------------------------

        if line.startswith("### TOPIC"):

            if list_open:
                output.append("</ol>")
                list_open = False

            if topic_open:
                output.append("</div>")

            topic_open = True

            title = line.replace("### ", "")

            output.append(f"""
            <div class="topic-card">
                <div class="topic-number">{html.escape(title)}</div>
            """)

            continue

        # -----------------------------------------
        # SECTION HEADINGS
        # -----------------------------------------

        if line.startswith("#### "):

            if list_open:
                output.append("</ol>")
                list_open = False

            heading = line.replace("#### ", "").strip()

            output.append(
                f'<div class="section-heading">{inline_format(heading)}</div>'
            )

            continue

        # -----------------------------------------
        # CATEGORY / SCORE / GS PAPER
        # -----------------------------------------

        if line.startswith("* **Category:**"):

            value = line.split("**Category:**", 1)[1].strip()

            output.append(
                f'<div class="meta-row">'
                f'<span class="badge category">🏷️ {inline_format(value)}</span>'
                f'</div>'
            )

            continue

        if line.startswith("* **UPSC Relevance Score:**"):

            value = line.split(
                "**UPSC Relevance Score:**",
                1
            )[1].strip()

            output.append(
                f'<span class="badge relevance">🎯 {inline_format(value)}</span>'
            )

            continue

        if line.startswith("* **GS Paper:**"):

            value = line.split(
                "**GS Paper:**",
                1
            )[1].strip()

            output.append(
                f'<span class="badge gs">📚 {inline_format(value)}</span>'
            )

            continue

        # -----------------------------------------
        # SOURCE
        # -----------------------------------------

        if line.startswith("* **Source Link:**"):

            value = line.split(
                "**Source Link:**",
                1
            )[1].strip()

            output.append(
                f"""
                <div class="source-box">
                    🔗 <strong>Source:</strong>
                    {inline_format(value)}
                </div>
                """
            )

            continue

        if line.startswith("* **Article Title:**"):

            value = line.split(
                "**Article Title:**",
                1
            )[1].strip()

            output.append(
                f'<div class="article-title">📰 {inline_format(value)}</div>'
            )

            continue

        # -----------------------------------------
        # NUMBERED LISTS
        # -----------------------------------------

        import re

        if re.match(r"^\d+\.", line):

            if not list_open:
                output.append("<ol>")
                list_open = True

            value = re.sub(
                r"^\d+\.\s*",
                "",
                line
            )

            output.append(
                f"<li>{inline_format(value)}</li>"
            )

            continue

        # -----------------------------------------
        # MCQ OPTIONS
        # -----------------------------------------

        if re.match(r"^[A-D]\)", line):

            output.append(
                f'<div class="option">{inline_format(line)}</div>'
            )

            continue

        # -----------------------------------------
        # QUICK REVISION / MCQ / MAINS HEADINGS
        # -----------------------------------------

        if line.startswith("### TOP 5 QUICK REVISION POINTS"):

            if topic_open:
                output.append("</div>")
                topic_open = False

            output.append("""
            <div class="special-card revision-card">
                <h2>⚡ Top 5 Quick Revision Points</h2>
            """)

            continue

        if line.startswith("### PRELIMS MCQs"):

            if topic_open:
                output.append("</div>")
                topic_open = False

            output.append("""
            <div class="special-card mcq-card">
                <h2>❓ Prelims MCQs</h2>
            """)

            continue

        if line.startswith("### MAINS PRACTICE QUESTION"):

            if topic_open:
                output.append("</div>")
                topic_open = False

            output.append("""
            <div class="special-card mains-card">
                <h2>✍️ Mains Practice</h2>
            """)

            continue

        if line.startswith("#### MCQ"):

            output.append(
                f'<h3>{inline_format(line.replace("#### ", ""))}</h3>'
            )

            continue

        # -----------------------------------------
        # CORRECT ANSWER
        # -----------------------------------------

        if line.startswith("**Correct Answer:**"):

            output.append(
                f"""
                <div class="answer">
                    {inline_format(line)}
                </div>
                """
            )

            continue

        # -----------------------------------------
        # HORIZONTAL RULE
        # -----------------------------------------

        if line.startswith("---"):

            output.append("<hr>")

            continue

        # -----------------------------------------
        # NORMAL CONTENT
        # -----------------------------------------

        output.append(
            f'<p>{inline_format(line)}</p>'
        )

    if list_open:
        output.append("</ol>")

    if topic_open:
        output.append("</div>")

    output.append("</div>")

    return "\n".join(output)


email_content = build_html(briefing)


html_email = f"""
<!DOCTYPE html>
<html>

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>UPSC Daily Current Affairs</title>

<style>

body {{
    margin: 0;
    padding: 0;
    background: #eef2f7;
    font-family: Arial, Helvetica, sans-serif;
    color: #1f2937;
}}

.container {{
    max-width: 760px;
    margin: 30px auto;
    background: #ffffff;
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 4px 18px rgba(0,0,0,0.08);
}}

.header {{
    background: #172554;
    color: white;
    padding: 32px 25px;
    text-align: center;
}}

.header h1 {{
    margin: 0;
    font-size: 28px;
}}

.header p {{
    margin: 8px 0 0;
    opacity: 0.85;
}}

.date {{
    margin-top: 14px;
    font-size: 13px;
    opacity: 0.75;
}}

.content {{
    padding: 25px;
}}

.topic-card {{
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    margin-bottom: 22px;
    padding: 22px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}}

.topic-number {{
    font-size: 21px;
    font-weight: bold;
    color: #172554;
    margin-bottom: 16px;
}}

.section-heading {{
    margin-top: 20px;
    margin-bottom: 8px;
    font-weight: bold;
    font-size: 14px;
    color: #334155;
    text-transform: uppercase;
}}

.meta-row {{
    margin-bottom: 10px;
}}

.badge {{
    display: inline-block;
    padding: 6px 10px;
    margin: 3px 5px 3px 0;
    border-radius: 20px;
    font-size: 12px;
    font-weight: bold;
}}

.category {{
    background: #e0f2fe;
    color: #075985;
}}

.relevance {{
    background: #fef3c7;
    color: #92400e;
}}

.gs {{
    background: #ede9fe;
    color: #5b21b6;
}}

p {{
    font-size: 15px;
    line-height: 1.7;
    margin: 8px 0;
}}

strong {{
    color: #111827;
}}

ol {{
    padding-left: 25px;
}}

li {{
    margin-bottom: 10px;
    line-height: 1.6;
}}

.source-box {{
    margin-top: 18px;
    padding: 12px;
    background: #f8fafc;
    border-radius: 8px;
    font-size: 13px;
}}

.source-box a {{
    color: #2563eb;
    font-weight: bold;
    text-decoration: none;
}}

.article-title {{
    font-size: 13px;
    color: #64748b;
    margin-top: 10px;
}}

.option {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 7px;
    padding: 9px 12px;
    margin: 6px 0;
}}

.answer {{
    margin-top: 12px;
    padding: 11px;
    background: #ecfdf5;
    border-left: 4px solid #10b981;
    border-radius: 6px;
}}

.special-card {{
    margin-top: 25px;
    padding: 22px;
    border-radius: 12px;
}}

.special-card h2 {{
    margin-top: 0;
}}

.revision-card {{
    background: #eff6ff;
    border: 1px solid #bfdbfe;
}}

.mcq-card {{
    background: #faf5ff;
    border: 1px solid #ddd6fe;
}}

.mains-card {{
    background: #fff7ed;
    border: 1px solid #fed7aa;
}}

hr {{
    border: 0;
    border-top: 1px solid #e2e8f0;
    margin: 20px 0;
}}

.footer {{
    background: #f8fafc;
    padding: 20px 25px;
    text-align: center;
    color: #64748b;
    font-size: 12px;
    line-height: 1.6;
}}

@media only screen and (max-width: 600px) {{

    .container {{
        margin: 0;
        border-radius: 0;
    }}

    .content {{
        padding: 16px;
    }}

    .topic-card {{
        padding: 17px;
    }}

    .header h1 {{
        font-size: 23px;
    }}

}}

</style>

</head>

<body>

<div class="container">

    <div class="header">

        <h1>🇮🇳 UPSC Daily Current Affairs</h1>

        <p>AI-powered Civil Services Briefing</p>

        <div class="date">
            {today}
        </div>

    </div>

    <div class="content">

        {email_content}

    </div>

    <div class="footer">

        <strong>UPSC AI News Agent</strong>
        <br>

        Generated automatically from current news.

        <br><br>

        ⚠️ Always verify important facts with
        authoritative sources before using them
        in an examination.

    </div>

</div>

</body>

</html>
"""


# ============================================================
# 8. SEND EMAIL
# ============================================================

sender = os.environ["GMAIL_USERNAME"]

app_password = os.environ["GMAIL_APP_PASSWORD"]

recipient = sender


message = MIMEMultipart("alternative")

message["Subject"] = (
    "UPSC Daily Current Affairs - AI Briefing"
)

message["From"] = sender

message["To"] = recipient


message.attach(
    MIMEText(
        briefing,
        "plain",
        "utf-8"
    )
)


message.attach(
    MIMEText(
        html_email,
        "html",
        "utf-8"
    )
)


print("\nSending email...")


with smtplib.SMTP(
    "smtp.gmail.com",
    587
) as server:

    server.starttls()

    server.login(
        sender,
        app_password
    )

    server.sendmail(
        sender,
        recipient,
        message.as_string()
    )


print("\n====================================")
print("EMAIL SENT SUCCESSFULLY")
print("====================================")
