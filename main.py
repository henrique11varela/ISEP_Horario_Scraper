import time, json
from flask import Flask, render_template, redirect
from selenium import webdriver
from selenium.webdriver import Chrome, ChromeService
from selenium.webdriver.common.by import By
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

with open('./config.json') as config_file:
    config = json.load(config_file)
    sources = config["sources"]
    creds = config["creds"]
    production = config["production"]

def login(driver: Chrome):
    try:
        driver.get("https://portal.isep.ipp.pt/")
        driver.implicitly_wait(2)
        driver.find_element(By.ID, "ContentPlaceHolderMain_txtLoginISEP").send_keys(creds["user"])
        driver.find_element(By.ID, "ContentPlaceHolderMain_txtPasswordISEP").send_keys(creds["pass"])
        driver.find_element(By.ID, "ContentPlaceHolderMain_btLoginISEP").click()
    except Exception as e:
        print("login", flush=True)
        print(e, flush=True)

def scrape_url(driver: Chrome, url: str):
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

output = get_everything(sources)

def my_scheduled_task():
    global output
    print("here", flush=True)
    output = get_everything(sources)

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
    return render_template("index.html", turmas=list(output))

@app.get("/<turma>")
def horarios_templates(turma=None):
    if turma not in list(output):
        return redirect("/")
    days = []
    for day in list(order_day):
        days.append({
            "week": day,
            "day": order_day[day]
        })
    return render_template("days.html", output=output, days=days, turma=turma)

@app.get("/<turma>/<dia>")
def horarios_dias_templates(turma=None, dia=None):
    if turma not in list(output):
        return redirect("/")
    dia_int = int(dia)
    if dia_int < 0 or dia_int > 6:
        return redirect(f"/{turma}")
    classes = {}
    for day in output[turma]:
        if order_day[day['weekday']] == int(dia):
            day['classes'].sort(key=lambda x: int(x['hours_start'].replace(':', '')))
            classes = day
            break
    return render_template("classes.html", output=output, classes=classes, turma=turma)


print("#-# Starting")
try:
    app.run(host="0.0.0.0", port=5000)
except Exception as e:
    print("#-# Error")
    print(e)
