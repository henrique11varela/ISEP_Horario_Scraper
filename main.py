import os, time, datetime, sqlite3
from dotenv import load_dotenv
from flask import Flask, render_template, redirect
from selenium import webdriver
from selenium.webdriver import Chrome, ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from apscheduler.schedulers.background import BackgroundScheduler

order_day = {
    "SEGUNDA-FEIRA": 0,
    "TERÇA-FEIRA": 1,
    "QUARTA-FEIRA": 2,
    "QUINTA-FEIRA": 3,
    "SEXTA-FEIRA": 4,
    "SÁBADO": 5,
    "DOMINGO": 6
}

load_dotenv()

HORARIO_URL = "https://portal.isep.ipp.pt/intranet/ver_horario/ver_horario.aspx?class="

# SOURCES is a comma-separated list of turma:class_id pairs, e.g. "1NA:53466,1NB:53467"
sources = []
for pair in os.environ["SOURCES"].split(","):
    turma, class_id = pair.strip().split(":")
    sources.append({"turma": turma.strip(), "link": HORARIO_URL + class_id.strip()})
creds = {"user": os.environ["ISEP_USER"], "pass": os.environ["ISEP_PASS"]}
production = os.environ.get("PRODUCTION", "true").lower() in ("1", "true", "yes")
db_path = os.environ.get("DB_PATH", "./horario.db")
port = int(os.environ.get("PORT", "5000"))

def get_db():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS days (
                turma TEXT NOT NULL,
                weekday TEXT NOT NULL,
                date TEXT NOT NULL,
                PRIMARY KEY (turma, weekday)
            );
            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turma TEXT NOT NULL,
                weekday TEXT NOT NULL,
                hours_start TEXT NOT NULL,
                hours_end TEXT NOT NULL,
                class_name TEXT NOT NULL,
                prof_name TEXT NOT NULL,
                classroom TEXT NOT NULL,
                FOREIGN KEY (turma, weekday) REFERENCES days (turma, weekday)
            );
        """)
    conn.close()

def save_output(output):
    # Replace each scraped turma's schedule in a single transaction
    conn = get_db()
    with conn:
        for turma, days in output.items():
            conn.execute("DELETE FROM classes WHERE turma = ?", (turma,))
            conn.execute("DELETE FROM days WHERE turma = ?", (turma,))
            for day in days:
                conn.execute(
                    "INSERT INTO days (turma, weekday, date) VALUES (?, ?, ?)",
                    (turma, day["weekday"], day["date"])
                )
                conn.executemany(
                    "INSERT INTO classes (turma, weekday, hours_start, hours_end, class_name, prof_name, classroom) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [(turma, day["weekday"], c["hours_start"], c["hours_end"], c["class_name"], c["prof_name"], c["classroom"]) for c in day["classes"]]
                )
    conn.close()

def get_turmas():
    conn = get_db()
    turmas = [row["turma"] for row in conn.execute("SELECT DISTINCT turma FROM days ORDER BY turma")]
    conn.close()
    return turmas

def get_day(turma, weekday):
    conn = get_db()
    day = conn.execute("SELECT weekday, date FROM days WHERE turma = ? AND weekday = ?", (turma, weekday)).fetchone()
    if day is None:
        conn.close()
        return {"weekday": weekday, "date": "", "classes": []}
    rows = conn.execute(
        """SELECT hours_start, hours_end, class_name, prof_name, classroom FROM classes
           WHERE turma = ? AND weekday = ?
           ORDER BY CAST(REPLACE(hours_start, ':', '') AS INTEGER)""",
        (turma, weekday)
    ).fetchall()
    conn.close()
    return {"weekday": day["weekday"], "date": day["date"], "classes": [dict(r) for r in rows]}

def login(driver: Chrome):
    print('logging in', flush=True)
    try:
        driver.get("https://portal.isep.ipp.pt/")
        driver.implicitly_wait(2)
        driver.find_element(By.ID, "ContentPlaceHolderMain_txtLoginISEP").send_keys(creds["user"])
        driver.find_element(By.ID, "ContentPlaceHolderMain_txtPasswordISEP").send_keys(creds["pass"])
        login_button = driver.find_element(By.ID, "ContentPlaceHolderMain_btLoginISEP")
        login_button.click()
        # Wait for the post-login redirect to finish, otherwise it can override the first timetable page
        wait = WebDriverWait(driver, 15)
        wait.until(EC.staleness_of(login_button))
        wait.until(EC.invisibility_of_element_located((By.ID, "ContentPlaceHolderMain_txtLoginISEP")))
        wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
    except Exception as e:
        print("login", flush=True)
        print(e, flush=True)

def scrape_url(driver: Chrome, url: str):
    print(f'going for: {url}', flush=True)
    driver.get(url)
    time.sleep(1)
    driver.save_screenshot(f'{url.split("=")[-1]}.png')
    week_days = [el.text.split("\n") for el in driver.find_elements(By.CSS_SELECTOR, ".wc-day-column-header")]
    output = []
    
    day_elements = driver.find_elements(By.CSS_SELECTOR, ".wc-day-column-inner")
    for idx, day_element in enumerate(day_elements):
        class_elements = day_element.find_elements(By.CSS_SELECTOR, ".wc-cal-event.classes")
        day = {
            "weekday": week_days[idx][0],
            "date": week_days[idx][1],
            "classes": []
        }
        for class_element in class_elements:
            hours_start, hours_end = class_element.find_element(By.CSS_SELECTOR, ".wc-time").text.split(" até ")

            prof_name, classroom = [b.text for b in class_element.find_elements(By.CSS_SELECTOR, ".wc-body b")]
            
            class_name = class_element.find_element(By.CSS_SELECTOR, "a[title='Disciplina']").text
            
            day["classes"].append({
                "hours_start": hours_start,
                "hours_end": hours_end,
                "class_name": class_name[:5],
                "prof_name": prof_name,
                "classroom": classroom
            })
        output.append(day)
    return output

def get_everything(sources):
    try:
        print("Starting WebDriver...")
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")   # required for servers
        options.add_argument("--window-size=1920,2160")
        options.add_argument("--no-sandbox")
        service = ChromeService("/usr/bin/chromedriver")
        driver = Chrome(service=service, options=options)
        login(driver)
        output = {}
        for item in sources:
            output[item["turma"]] = scrape_url(driver, item["link"])
        driver.close()
        return output
    except Exception as e:
        print(e)

def refresh():
    output = get_everything(sources) or {}
    # An empty schedule means the scrape failed (e.g. bad login), so keep the stored one
    output = {turma: days for turma, days in output.items() if days}
    if output:
        save_output(output)

init_db()
refresh()

def my_scheduled_task():
    print("here", flush=True)
    refresh()

scheduler = BackgroundScheduler()
scheduler.add_job(
    func=my_scheduled_task,
    trigger="cron",
    hour=12,
    minute=0
)

scheduler.start()

app = Flask(__name__)
if not production:
    from flask_cors import CORS
    CORS(app, support_credentials=True)

@app.get("/")
def index():
    return render_template("index.html", turmas=get_turmas())

@app.get("/<turma>")
def horarios_templates(turma=None):
    if turma not in get_turmas():
        return redirect("/")
    days = []
    now = datetime.datetime.now()
    weekday = now.weekday()
    for day in list(order_day):
        days.append({
            "week": day,
            "day": order_day[day],
            "now": weekday == order_day[day]
        })
    return render_template("days.html", days=days, turma=turma)

@app.get("/<turma>/<dia>")
def horarios_dias_templates(turma=None, dia=None):
    if turma not in get_turmas():
        return redirect("/")
    dia_int = int(dia)
    if dia_int < 0 or dia_int > 6:
        return redirect(f"/{turma}")
    weekday = next(name for name, idx in order_day.items() if idx == dia_int)
    classes = get_day(turma, weekday)
    now = datetime.datetime.now()
    hour = now.hour
    minute = now.minute
    if minute < 10:
        minute = f'0{minute}'
    int_now = int(f"{hour}{minute}")
    for class_instance in classes['classes']:
        if int(class_instance['hours_start'].replace(':', '')) - 10 <= int_now and int(class_instance['hours_end'].replace(':', '')) >= int_now:
            class_instance['now'] = True
        else:
            class_instance['now'] = False
    return render_template("classes.html", classes=classes, turma=turma)


print("#-# Starting")
try:
    app.run(host="0.0.0.0", port=port)
except Exception as e:
    print("#-# Error")
    print(e)
