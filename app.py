from flask import Flask, Blueprint, render_template, request, redirect, url_for, session, current_app
import openai
import os
import time
import hashlib
import logging
import markdown
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "your_secret_key")

# Setup Rate Limiting (e.g., max 100 requests per hour per IP)
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["100 per hour"])

# Setup Caching (simple in-memory cache)
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 300})

# Set up OpenAI client using environment variable
openai.api_key = os.getenv("OPENAI_API_KEY_ELUCIDATE")

# Define the 6 dream questions and labels
QUESTIONS = [
    "Hello! What did you dream about last night? Describe the setting as best you can.",
    "Tell me more about one specific detail, figure, or symbol that stood out to you.",
    "What emotions did you feel throughout the dream?",
    "Did anything in your dream feel particularly meaningful or symbolic?",
    "What thoughts or emotions did you have upon waking up?",
    "If you could step back into the dream right now, what would you do or explore further?"
]

LABELS = [
    "Dream Narrative & Atmosphere",
    "Core Focus and Symbolic Anchor",
    "Emotional Undercurrents",
    "Latent Messages, Personal Symbols",
    "Lingering Impact & Subconscious Echo",
    "Unfinished Exploration & Desire"
]
# Global list for storing dream diary entries (in production use a DB)
dream_diary = []

# Create a blueprint for main routes
main_bp = Blueprint("main", __name__)

def build_prompt(responses):
    """Formats the dream responses into a structured prompt for the AI."""
    prompt = (
        "You are a professional dream interpreter. You are trained in both the classics and modern schools of thought. "
        "You take into account spirituality as well as psychology. Try to combine meanings between dream elements "
        "and interpretations. Do not be afraid to make connections between those elements, "
        "treat them as interconnected. Connect with the user, and speak to them directly. "
        "Based on the following responses, provide a thoughtful and insightful interpretation of the dream. "
        "Avoid literal and obvious interpretations. "
        "Avoid a summary paragraph, but instead end with a self-reflective question or insight that encourages deeper personal exploration.\n\n"
    )
    for label, response in zip(LABELS, responses):
        if response.strip():
            prompt += f"{label}: {response}\n"
    return prompt

def generate_interpretation(prompt):
    """Calls OpenAI API to get a dream interpretation, with caching and improved error handling."""
    # Create a cache key from the prompt
    prompt_hash = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
    cached_interpretation = cache.get(prompt_hash)
    if cached_interpretation:
        current_app.logger.info("Returning cached interpretation.")
        return cached_interpretation

    try:
        # Simulate delay (for demonstration)
        time.sleep(5)
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": prompt + "You are a professional dream interpreter."},
                {"role": "user", "content": prompt + "\n\nLimit the response to 250 words. Use rich text formatting with paragraphs, bold where necessary, and bullet points if applicable."}
            ],
            temperature=1.2
        )
        interpretation = response.choices[0].message.content.strip()
        # Enforce word limit
        words = interpretation.split()
        if len(words) > 250:
            interpretation = " ".join(words[:250]) + "..."
        cache.set(prompt_hash, interpretation)
        return interpretation
    except Exception as e:
        current_app.logger.error("Error during OpenAI API call", exc_info=True)
        return "Sorry, we encountered an error while generating your interpretation. Please try again later."

# Homepage route: Welcome page
@main_bp.route("/")
def home():
    return render_template("index.html")

# Start route: Resets questionnaire and moves to first question
@main_bp.route("/start", methods=["GET", "POST"])
@limiter.limit("10 per minute")  # Additional rate limit on starting the questionnaire
def start():
    session["responses"] = [""] * len(QUESTIONS)
    session["current_question"] = 0
    return redirect(url_for("main.question"))

# Questionnaire route: Show one question at a time
@main_bp.route("/question", methods=["GET", "POST"])
@limiter.limit("30 per minute")
def question():
    current_question = session.get("current_question", 0)
    if request.method == "POST":
        answer = request.form.get("answer", "").strip()
        if "skip" in request.form:
            answer = ""
        responses = session.get("responses", [""] * len(QUESTIONS))
        responses[current_question] = answer
        session["responses"] = responses
        if current_question + 1 < len(QUESTIONS):
            session["current_question"] = current_question + 1
            return redirect(url_for("main.question"))
        else:
            return redirect(url_for("main.review"))
    return render_template("question.html", question=QUESTIONS[current_question], q_num=current_question + 1)

# Review route: Allow user to review and edit responses before final submission
@main_bp.route("/review", methods=["GET", "POST"])
@limiter.limit("15 per minute")
def review():
    responses = session.get("responses", [""] * len(QUESTIONS))
    prompt = build_prompt(responses)
    if request.method == "POST":
        # Allow editing; update responses based on form input and redirect to loading page if confirmed.
        for i in range(len(QUESTIONS)):
            responses[i] = request.form.get(f"question_{i}", "").strip()
        session["responses"] = responses
        return redirect(url_for("main.loading"))
    return render_template("review.html", questions=QUESTIONS, responses=responses, prompt=prompt)

# Loading route: Display loading screen while AI processes interpretation
@main_bp.route("/loading")
def loading():
    return render_template("loading.html")

# Result route: Display the final interpretation with regeneration and feedback buttons
@main_bp.route("/result", methods=["GET"])
def result():
    responses = session.get("responses", [""] * len(QUESTIONS))
    prompt = build_prompt(responses)
    interpretation = generate_interpretation(prompt)
    
    # Convert Markdown to HTML
    interpretation_html = markdown.markdown(interpretation)
    
    return render_template("result.html", interpretation=interpretation_html)

# Dream Diary route: Display past interpretations
@main_bp.route("/diary", methods=["GET"])
def diary():
    return render_template("diary.html", diary_entries=dream_diary)

# Register blueprint with the Flask app
app.register_blueprint(main_bp)

if __name__ == "__main__":
    app.run(debug=True, port=5001)
