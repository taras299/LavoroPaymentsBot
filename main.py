import telebot
from telebot import types
from sqlalchemy import create_engine, Column, Integer, String, Sequence, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import SQLAlchemyError
import logging
import time
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, Sequence('user_id_seq'), primary_key=True)
    username = Column(String(50))
    is_banned = Column(Boolean, default=False)

class Payment(Base):
    __tablename__ = 'payments'
    id = Column(Integer, Sequence('payment_id_seq'), primary_key=True)
    user_id = Column(Integer)
    username = Column(String(50))
    link = Column(String(255))
class PaymentRequest(Base):
    __tablename__ = 'payment_requests'
    id = Column(Integer, Sequence('payment_request_id_seq'), primary_key=True)
    user_id = Column(Integer)
    last_request_time = Column(Integer)  

engine = create_engine('sqlite:///bot.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

bot_token = "API KEY BOTFATHER"
bot = telebot.TeleBot(bot_token)

admin_ids = ['admins id']
group_chat_id = group id

user_payment_request = {}
user_payment_change_request = {}
user_links = {}

def send_notification_to_group(message):
    try:
        bot.send_message(group_chat_id, message)
    except telebot.apihelper.ApiTelegramException as e:
        logger.error(f"Failed to send message to group: {e}")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    username = message.from_user.username
    user_id = message.from_user.id
    try:
        user = session.query(User).filter(User.username == username).first()
        if not user:
            new_user = User(username=username)
            session.add(new_user)
            session.commit()
        elif user.is_banned:
            bot.send_message(message.chat.id, "❌Вас запетушили и запретили использование бота.")
            return
    except SQLAlchemyError as e:
        bot.send_message(message.chat.id, "Произошла ошибка при взаимодействии с базой данных.")
        logger.error(f"Database error in /start: {e}")
        return

    markup = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton("💸Получить выплату💸", callback_data='get_payment')
    markup.add(button)
    bot.send_message(message.chat.id, "Добро пожаловать! Нажмите кнопку ниже, чтобы получить выплату🤑", reply_markup=markup)
    
    send_notification_to_group(f"@{username}|{user_id}|Выполнил команду /start")

@bot.message_handler(commands=['change'])
def change_link(message):
    username = message.from_user.username
    user_id = message.from_user.id

    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user and user.is_banned:
            bot.send_message(message.chat.id, "❌Вас запетушили и запретили использование бота.")
            return

        payment = session.query(Payment).filter(Payment.user_id == user_id).first()
        if payment:
            bot.send_message(message.chat.id, "Отправьте новый многоразовый счет.")
            user_payment_change_request[user_id] = True
            send_notification_to_group(f"@{username}|{user_id}|Выполнил команду /change")
        else:
            bot.send_message(message.chat.id, "У вас еще нет сохраненной ссылки.")
    except SQLAlchemyError as e:
        bot.send_message(message.chat.id, "Произошла ошибка при взаимодействии с базой данных.")
        logger.error(f"Database error in /change: {e}")

@bot.message_handler(commands=['ban'])
def ban_user(message):
    if str(message.from_user.id) not in admin_ids:
        return
    
    try:
        target_username = message.text.split()[1].lstrip('@')
        user = session.query(User).filter(User.username == target_username).first()
        if user:
            user.is_banned = True
            session.commit()
            bot.send_message(message.chat.id, f"Пользователь @{target_username} заблокирован.")
        else:
            bot.send_message(message.chat.id, f"Пользователь @{target_username} не найден.")
    except IndexError:
        bot.send_message(message.chat.id, "Пожалуйста, укажите имя пользователя для блокировки.")
    except SQLAlchemyError as e:
        bot.send_message(message.chat.id, "Произошла ошибка при взаимодействии с базой данных.")
        logger.error(f"Database error in /ban: {e}")

@bot.message_handler(commands=['unban'])
def unban_user(message):
    if str(message.from_user.id) not in admin_ids:
        return
    
    try:
        target_username = message.text.split()[1].lstrip('@')
        user = session.query(User).filter(User.username == target_username).first()
        if user:
            user.is_banned = False
            session.commit()
            bot.send_message(message.chat.id, f"Пользователь @{target_username} разблокирован.")
        else:
            bot.send_message(message.chat.id, f"Пользователь @{target_username} не найден.")
    except IndexError:
        bot.send_message(message.chat.id, "Пожалуйста, укажите имя пользователя для разблокировки.")
    except SQLAlchemyError as e:
        bot.send_message(message.chat.id, "Произошла ошибка при взаимодействии с базой данных.")
        logger.error(f"Database error in /unban: {e}")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    global user_payment_request, user_payment_change_request, user_links
    username = call.from_user.username
    user_id = call.from_user.id
    
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user and user.is_banned:
            bot.send_message(call.message.chat.id, "❌Вас запетушили и запретили использование бота.")
            return
    except SQLAlchemyError as e:
        bot.send_message(call.message.chat.id, "Произошла ошибка при взаимодействии с базой данных.")
        logger.error(f"Database error in callback_query: {e}")
        return

    if call.data == 'get_payment':
        payment_request = session.query(PaymentRequest).filter(PaymentRequest.user_id == user_id).first()
        current_time = int(time.time())

        if payment_request:
            time_since_last_request = current_time - payment_request.last_request_time
            if time_since_last_request < 3600:  
                bot.send_message(call.message.chat.id, "Выплату можно запросить раз в час!")
                return
        
        if payment_request:
            payment_request.last_request_time = current_time
        else:
            payment_request = PaymentRequest(user_id=user_id, last_request_time=current_time)
            session.add(payment_request)
        session.commit()

        user_payment_request[user_id] = True
        
        user = session.query(Payment).filter(Payment.user_id == user_id).first()
        if user and user.link:
            markup = types.InlineKeyboardMarkup()
            yes_button = types.InlineKeyboardButton("Да", callback_data='use_old_link')
            no_button = types.InlineKeyboardButton("Нет", callback_data='enter_new_link')
            markup.add(yes_button, no_button)
            bot.send_message(call.message.chat.id, "Использовать старую ссылку?", reply_markup=markup)
        else:
            bot.send_message(call.message.chat.id, "Пришлите ссылку на многоразовый счет CryptoBot для получения выплаты💰.\n\nИнструкция по созданию счета: https://telegra.ph/Kak-poluchit-mnogorazovyj-schet-v-kriptobote-05-24")
        
        send_notification_to_group(f"@{username}|{user_id}|Нажал на кнопку 'Получить выплату'")

    elif call.data == 'use_old_link':
        user = session.query(Payment).filter(Payment.user_id == user_id).first()
        if user:
            markup = types.InlineKeyboardMarkup()
            paid_button = types.InlineKeyboardButton("Выплачено", callback_data=f'paid_{user_id}')
            markup.add(paid_button)
            for admin_id in admin_ids:
                bot.send_message(admin_id, f"Новый платеж:\nНикнейм: @{user.username}\nID пользователя: {user_id}\nСсылка: {user.link}", reply_markup=markup)
            bot.send_message(call.message.chat.id, "Запрос на выплату принят. В течении часа ожидайте зачисления средств.")
            send_notification_to_group(f"@{username}|{user_id}|Подтвердил использование старой ссылки: {user.link}")
        
    elif call.data == 'enter_new_link':
        bot.send_message(call.message.chat.id, "Пожалуйста, введите новую ссылку")
        user_payment_request[user_id] = True
    
    elif call.data == 'confirm_link':
        if user_id in user_links:
            link = user_links[user_id]
            try:
                user = session.query(Payment).filter(Payment.user_id == user_id).first()
                if user:
                    user.link = link
                else:
                    user = Payment(user_id=user_id, username=username, link=link)
                    session.add(user)
                session.commit()
            except SQLAlchemyError as e:
                bot.send_message(call.message.chat.id, "Произошла ошибка при взаимодействии с базой данных.")
                logger.error(f"Database error in confirm_link: {e}")
                return

            markup = types.InlineKeyboardMarkup()
            paid_button = types.InlineKeyboardButton("Выплачено", callback_data=f'paid_{user_id}')
            markup.add(paid_button)
            for admin_id in admin_ids:
                bot.send_message(admin_id, f"Новый платеж:\nНикнейм: @{username}\nID пользователя: {user_id}\nСсылка: {link}", reply_markup=markup)

            bot.send_message(call.message.chat.id, "Запрос на выплату принят. В течении часа ожидайте зачисления средств.")
            send_notification_to_group(f"@{username}|{user_id}|Подтвердил ссылку: {link}")
            
            user_payment_request[user_id] = False
            user_payment_change_request[user_id] = False
            del user_links[user_id]

    elif call.data == 'reject_link':
        bot.send_message(call.message.chat.id, "Пожалуйста, введите новую ссылку:")
        user_payment_request[user_id] = True
        user_payment_change_request[user_id] = False
        send_notification_to_group(f"@{username}|{user_id}|Отклонил введённую ссылку и выбрал ввести новую")

    elif call.data.startswith('paid_'):
        user_id = int(call.data.split('_')[1])
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
            bot.send_message(call.message.chat.id, f"Платеж для пользователя {user_id} выплачен.")
            bot.send_message(user_id, "🎉Выплата успешно обработана и отправлена на ваш счет.")
        except Exception as e:
            logger.error(f"Error processing payment confirmation: {e}")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    global user_payment_request, user_payment_change_request, user_links
    username = message.from_user.username
    user_id = message.from_user.id
    link = message.text

    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user and user.is_banned:
            bot.send_message(message.chat.id, "❌Вас запетушили и запретили использование бота.")
            return
    except SQLAlchemyError as e:
        bot.send_message(message.chat.id, "Произошла ошибка при взаимодействии с базой данных.")
        logger.error(f"Database error in handle_message: {e}")
        return

    if user_id not in user_payment_request and user_id not in user_payment_change_request:
        bot.send_message(message.chat.id, "Ошибка: неизвестный запрос.")
        return

    if user_id in user_payment_request and user_payment_request[user_id]:
        user_links[user_id] = link
        markup = types.InlineKeyboardMarkup()
        confirm_button = types.InlineKeyboardButton("Да", callback_data='confirm_link')
        reject_button = types.InlineKeyboardButton("Нет", callback_data='reject_link')
        markup.add(confirm_button, reject_button)
        bot.send_message(message.chat.id, f"Вы хотите использовать эту ссылку?\n{link}", reply_markup=markup)
        user_payment_request[user_id] = False
    
    if user_id in user_payment_change_request and user_payment_change_request[user_id]:
        try:
            payment = session.query(Payment).filter(Payment.user_id == user_id).first()
            if payment:
                payment.link = link
                session.commit()
                bot.send_message(message.chat.id, "Ссылка успешно обновлена.")
                send_notification_to_group(f"@{username}|{user_id}|Обновил ссылку на: {link}")
            else:
                bot.send_message(message.chat.id, "У вас еще нет сохраненной ссылки.")
        except SQLAlchemyError as e:
            bot.send_message(message.chat.id, "Произошла ошибка при взаимодействии с базой данных.")
            logger.error(f"Database error in update link: {e}")
        user_payment_change_request[user_id] = False

while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        logger.error(f"Bot polling error: {e}")
        time.sleep(15)
