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
# 7. CREATE EMAIL
# ============================================================

escaped_briefing = html.escape(briefing)

email_content = escaped_briefing.replace(
    "\n",
    "<br>"
)

html_email = f"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<style>

body {{
    font-family: Arial, Helvetica, sans-serif;
    line-height: 1.6;
    background: #f5f5f5;
    margin: 0;
    padding: 20px;
}}

.container {{
    max-width: 800px;
    margin: auto;
    background: white;
    padding: 30px;
    border-radius: 10px;
}}

.header {{
    text-align: center;
    padding-bottom: 20px;
    border-bottom: 2px solid #eeeeee;
}}

.content {{
    margin-top: 25px;
    font-size: 15px;
}}

.footer {{
    margin-top: 30px;
    padding-top: 15px;
    border-top: 1px solid #eeeeee;
    color: #777777;
    font-size: 12px;
}}

</style>

</head>

<body>

<div class="container">

<div class="header">

<h1>UPSC Daily Current Affairs</h1>

<p>AI-generated daily briefing</p>

</div>

<div class="content">

{email_content}

</div>

<div class="footer">

Generated automatically by the UPSC AI News Agent.

<br>

Always verify important facts with authoritative
sources before using them in an examination.

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
