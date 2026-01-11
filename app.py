import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from flask_admin import Admin
from flask_admin.form import ImageUploadField
from flask_admin.contrib.sqla import ModelView
from flask_admin import AdminIndexView, expose

load_dotenv() 

UPLOAD_FOLDER = 'static/uploads/'  
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

app = Flask(__name__)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///flights.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Flight(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    departure_city = db.Column(db.String(100), nullable=False)
    arrival_city = db.Column(db.String(100), nullable=False)
    image = db.Column(db.String(255))
    description = db.Column(db.Text)
    route = db.Column(db.String(255))
    departure_datetime = db.Column(db.DateTime, nullable=False)
    arrival_datetime = db.Column(db.DateTime, nullable=False)
    price = db.Column(db.Float, nullable=False)
    
    bookings = db.relationship('Booking', foreign_keys='Booking.flight_id')


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flight_id = db.Column(db.Integer, db.ForeignKey('flight.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)

    flight = db.relationship('Flight', foreign_keys=[flight_id]) 
    user = db.relationship('User', foreign_keys=[user_id]) 

class MyAdminIndexView(AdminIndexView):
    @expose('/')
    def index(self):
        if not current_user.is_authenticated or current_user.username != 'admin':
            return redirect(url_for('login'))
        return super(MyAdminIndexView, self).index()


admin = Admin(app, name='Flight Booking Admin', template_mode='bootstrap3', index_view=MyAdminIndexView())

class MyModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.username == 'admin'

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))
    
    can_create = True
    can_edit = True
    can_delete = True
    form_overrides = {
        'image_path': ImageUploadField,
    }
    column_exclude_list = ['password_hash'] # не показывать пароль в админке
    

admin.add_view(MyModelView(Flight, db.session))
admin.add_view(MyModelView(Booking, db.session))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    add_default_flights() 
    flights = Flight.query.all()
    return render_template('index.html', flights=flights)

@app.route('/about')
def about():    
    return render_template('about.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Имя пользователя уже занято.')
            return redirect(url_for('register'))

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Регистрация прошла успешно. Теперь вы можете войти.')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль.')
            return redirect(url_for('login'))
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/flights/<int:flight_id>')
def flight_details(flight_id):
    flight = Flight.query.get_or_404(flight_id)
    duration = flight.arrival_datetime - flight.departure_datetime
    duration_hours = int(duration.total_seconds()) // 3600  
    duration_minutes = int((duration.total_seconds() % 3600) // 60)  # Остаток минут
    return render_template('flight_details.html', flight=flight, duration_hours=duration_hours, duration_minutes = duration_minutes) 

@app.route('/flights/<int:flight_id>/book', methods=['POST'])
@login_required
def book_flight(flight_id):
    flight = Flight.query.get_or_404(flight_id)
    full_name = request.form['full_name']
    email = request.form['email']
    phone = request.form['phone']

    if not full_name or not email or not phone:
        flash('Пожалуйста, заполните все поля.')
        return redirect(url_for('flight_details', flight_id=flight_id))

    booking = Booking(flight_id=flight.id, user_id=current_user.id,
                      full_name=full_name, email=email, phone=phone)
    db.session.add(booking)
    db.session.commit()

    flash('Рейс успешно забронирован!')
    return redirect(url_for('bookings'))


@app.route('/bookings')
@login_required
def bookings():
    user_bookings = Booking.query.filter_by(user_id=current_user.id).all()
    return render_template('bookings.html', bookings=user_bookings)


def add_default_flights():
    if not Flight.query.first():  # Проверяем, есть ли хоть один рейс
        flights = [
            Flight(departure_city='Москва', arrival_city='Санкт-Петербург', image='static/uploads/moscow_spb.jpg', 
                            description='Прямой рейс из Москвы в Санкт-Петербург.', route='MOW-SPB',
                            departure_datetime=datetime(2024, 5, 10, 10, 0, 0), arrival_datetime=datetime(2024, 5, 10, 11, 30, 0),
                            price=3500.00),
             Flight(departure_city='Москва', arrival_city='Екатеринбург', image='static/uploads/moscow_ekb.jpg', 
                            description='Прямой рейс из Москвы в Екатеринбург.', route='MOW-EKB',
                            departure_datetime=datetime(2024, 5, 12, 14, 0, 0), arrival_datetime=datetime(2024, 5, 12, 17, 30, 0),
                            price=4200.00),
        ]
        db.session.add_all(flights)
        db.session.commit()


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)