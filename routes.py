from flask import render_template,request,session,redirect,url_for
from pyexpat.errors import messages
from datetime import date
from app import app,db
from app import User,Memory

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

        session['user_id'] = user.uid

    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()

    return redirect(url_for('login'))

@app.route('/create_memory',methods=['GET','POST'])
def create_memory():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'GET':
        return render_template ('create_memory.html')
    if request.method == 'POST':
        title = request.form['title']
        message = request.form['message']
        open_date = request.form['open_date']

    memory = Memory(title=title,message=message,open_date=date.fromisoformat(open_date),created_on=date.today(),user_id=session['user_id'])

    db.session.add(memory)
    db.session.commit()

    return f"Memory {title} created!"

@app.route('/my_memories')
def my_memories():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    memories = Memory.query.filter_by(user_id=session['user_id']).all()

    return render_template("my_memories.html",memories=memories,today=date.today())

@app.route('/test')
def test():
    return f"Session: {dict(session)}"

