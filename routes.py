from flask import render_template,request
from pyexpat.errors import messages

from app import app,db
from app import User

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup',methods=['GET','POST'])
def signup():
    if request.method == 'GET':
        return render_template('signup.html')
    elif request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User(username=username, password=password)

        db.session.add(user)
        db.session.commit()


        return f"Welcome {username}!!"

@app.route('/login',methods=['POST','GET'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    elif request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user is None :
            return "User not found"

        if user.password != password:
            return "Wrong password"


        return f"Welcome back {username}!"

@app.route('/create_memory',methods=['POST','GET'])
def create_memory():
    if request.method == 'GET':
        return render_template ('create_memory.html')
    if request.method == 'POST':
        title = request.form['title']
        message = request.form['message']
        open_date = request.form['open_date']

        return f"Memory {title} created!"

