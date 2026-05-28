# app.py
from flask import Flask, render_template, request, redirect, session, flash
import os
import uuid
import numpy as np
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing import image
import mysql.connector
from mysql.connector import pooling

app = Flask(__name__)
app.secret_key = "secret"

UPLOAD_FOLDER = "static/uploads/"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Charger le modèle une seule fois
model = load_model("model/vgg16_skin_cancer.h5")

# ─── DB : connexion fraîche à chaque requête ───────────────────────────────────
DB_CONFIG = dict(
    host="localhost",
    user="root",
    password="",
    database="skin_cancer_db"
)

def get_db():
    """Retourne une connexion MySQL fraîche (évite les curseurs périmés)."""
    return mysql.connector.connect(**DB_CONFIG)

# ─── FILTRE JINJA2 : normalise image_path → relatif à static/ ─────────────────
@app.template_filter('img_path')
def img_path_filter(raw):
    """
    Accepte n'importe quel format stocké en base :
      - "static/uploads/xxx.jpg"   → "uploads/xxx.jpg"
      - "static\\uploads\\xxx.jpg" → "uploads/xxx.jpg"
      - "uploads/xxx.jpg"          → "uploads/xxx.jpg"  (déjà bon)
    """
    if not raw:
        return ""
    clean = raw.replace("\\", "/")
    if clean.startswith("static/"):
        clean = clean[len("static/"):]
    return clean

# ─── LOGIN ─────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form["username"]
        pwd  = request.form["password"]
        conn = get_db()
        cur  = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE username=%s AND password=%s", (user, pwd))
        result = cur.fetchone()
        cur.close(); conn.close()
        if result:
            session["user"] = user
            flash("Login réussi ✔", "success")
            return redirect("/dashboard")
        else:
            flash("Erreur login ❌", "danger")
    return render_template("login.html")

# ─── DASHBOARD ─────────────────────────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")
    return render_template("dashboard.html")

# ─── PREDICT ───────────────────────────────────────────────────────────────────
@app.route("/predict", methods=["GET", "POST"])
def predict():
    if "user" not in session:
        return redirect("/")

    if request.method == "POST":
        try:
            name = request.form["name"]
            age  = request.form["age"]
            file = request.files["image"]

            if not file or file.filename == "":
                flash("Veuillez choisir une image", "warning")
                return redirect("/predict")

            # Nom unique pour éviter les conflits
            ext      = os.path.splitext(file.filename)[1].lower()
            unique   = str(uuid.uuid4())[:8]
            filename = f"{unique}{ext}"
            path     = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(path)
            # Path relatif à static/ pour url_for
            relative_path = "uploads/" + filename

            # Prétraitement
            img = image.load_img(path, target_size=(224, 224))
            img = image.img_to_array(img) / 255.0
            img = np.expand_dims(img, axis=0)

            # Prédiction
            pred   = float(model.predict(img)[0][0])
            result = "Malignant" if pred > 0.5 else "Benign"

            # Sauvegarder en base
            conn = get_db()
            cur  = conn.cursor()
            cur.execute(
                "INSERT INTO patients (name, age, result, probability, image_path) VALUES (%s,%s,%s,%s,%s)",
                (name, age, result, pred, relative_path)
            )
            conn.commit()
            cur.close(); conn.close()

            flash("Analyse réussie ✔", "success")
            return render_template("result.html",
                                   result=result,
                                   prob=round(pred * 100, 2),
                                   img=relative_path)

        except Exception as e:
            flash(f"Erreur système : {str(e)}", "danger")
            return redirect("/predict")

    return render_template("predict.html")

# ─── PATIENTS ──────────────────────────────────────────────────────────────────
@app.route("/patients")
def patients():
    if "user" not in session:
        return redirect("/")
    conn = get_db()
    cur  = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM patients ORDER BY created_at DESC")
    data = cur.fetchall()
    cur.close(); conn.close()
    return render_template("patients.html", patients=data)

# ─── STATS ─────────────────────────────────────────────────────────────────────
@app.route("/stats")
def stats():
    if "user" not in session:
        return redirect("/")
    conn = get_db()
    cur  = conn.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) AS total FROM patients")
    total = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS cnt FROM patients WHERE result='Malignant'")
    malignant = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) AS cnt FROM patients WHERE result='Benign'")
    benign = cur.fetchone()["cnt"]
    cur.close(); conn.close()
    return render_template("stats.html", total=total, malignant=malignant, benign=benign)

# ─── LOGOUT ────────────────────────────────────────────────────────────────────
@app.route("/logout")
def logout():
    session.clear()
    flash("Déconnecté", "info")
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)
