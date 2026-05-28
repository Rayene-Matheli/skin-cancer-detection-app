from flask import Flask, render_template, request, redirect, session, flash
import os
import numpy as np
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing import image
import mysql.connector

app = Flask(__name__)
app.secret_key = "secret"

UPLOAD_FOLDER = "static/uploads/"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

model = load_model("model/vgg16_skin_cancer.h5")

db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="skin_cancer_db"
)
cursor = db.cursor(dictionary=True)

# --- LOGIN ---
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form["username"]
        pwd = request.form["password"]
        cursor.execute("SELECT * FROM users WHERE username=%s AND password=%s", (user, pwd))
        result = cursor.fetchone()
        if result:
            session["user"] = user
            flash("Login réussi ✔", "success")
            return redirect("/dashboard")
        else:
            flash("Erreur login ❌", "danger")
    return render_template("login.html")

# --- DASHBOARD ---
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")
    return render_template("dashboard.html")

# --- PREDICT ---
@app.route("/predict", methods=["GET", "POST"])
def predict():
    if "user" not in session:
        return redirect("/")
    if request.method == "POST":
        try:
            name = request.form["name"]
            age = request.form["age"]
            file = request.files["image"]
            if file.filename == "":
                flash("Veuillez choisir une image", "warning")
                return redirect("/predict")
            path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(path)
            img = image.load_img(path, target_size=(224, 224))
            img = image.img_to_array(img) / 255.0
            img = np.expand_dims(img, axis=0)
            pred = model.predict(img)[0][0]
            result = "Malignant" if pred > 0.5 else "Benign"
            cursor.execute("""
                INSERT INTO patients (name, age, result, probability, image_path)
                VALUES (%s, %s, %s, %s, %s)
            """, (name, age, result, float(pred), path))
            db.commit()
            flash("Analyse réussie ✔", "success")
            return render_template("result.html", result=result, prob=round(pred * 100, 2), img=path)
        except Exception as e:
            flash(f"Erreur système ❌: {str(e)}", "danger")
            return redirect("/predict")
    return render_template("predict.html")

# --- PATIENTS ---
@app.route("/patients")
def patients():
    if "user" not in session:
        return redirect("/")
    cursor.execute("SELECT * FROM patients ORDER BY created_at DESC")
    data = cursor.fetchall()
    return render_template("patients.html", patients=data)

# --- STATISTIQUES ---
@app.route("/stats")
def stats():
    if "user" not in session:
        return redirect("/")
    cursor.execute("SELECT COUNT(*) as total FROM patients")
    total = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) as cnt FROM patients WHERE result='Malignant'")
    malignant = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(*) as cnt FROM patients WHERE result='Benign'")
    benign = cursor.fetchone()["cnt"]
    return render_template("stats.html", total=total, malignant=malignant, benign=benign)

# --- LOGOUT ---
@app.route("/logout")
def logout():
    session.clear()
    flash("Déconnecté", "info")
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)
