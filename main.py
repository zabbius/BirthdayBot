#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import telebot

from telebot import types
from asq import query
from datetime import datetime

from telebot_token import Token

time_format = '%Y-%m-%dT%H:%M:%S'


class Messages:
    Welcome = 'Добро пожаловать в команду {}'
    EnterPin = 'Введи пин-код команды'
    TaskNumber = 'Задание {}'
    SelectTask = 'Выберите задание'
    Word = 'Слово'
    WordNumber = 'Слово+Число'
    Number = 'Число'
    TaskDone = 'Вы полностью справились с заданием {}! Переходите к следующему заданию.'
    CorrectAnswer = 'И это правильный ответ!'
    WrongAnswer = 'Не понимаю, попробуй еще раз'
    ReplyTask = 'Повторить задание'
    Back = 'Назад'
    QuestComplete = 'Квест завершен успешно, время вашей команды: {}'


class Task:
    def __init__(self, zone, text, format, *answers):
        self.zone = zone
        self.text = text
        self.format = format
        self.answers = {a.lower() for a in answers}

    def __str__(self):
        return (
            "Играющая зона: {zone}\r\n"
            "Задание: {text}\r\n"
            "Формат проверочного кода: {format}\r\n"
        ).format(zone=self.zone, text=self.text, format=self.format)


task_chains = [
    [
        Task("zone1", "task_chain_1_1", Messages.Word, "answer_1_1", "1_1"),
        Task("zone3", "task_chain_1_2", Messages.Word, "answer_1_2"),
        Task("zone2", "task_chain_1_3", Messages.Word, "answer_1_3"),
    ],
    [
        Task("zone1", "task_chain_2_1", Messages.Word, "answer_2_1"),
        Task("zone3", "task_chain_2_2", Messages.Word, "answer_2_2"),
        Task("zone2", "task_chain_2_3", Messages.Word, "answer_2_3"),
    ],
    [
        Task("zone1", "task_chain_3_1", Messages.Word, "answer_3_1"),
        Task("zone3", "task_chain_3_2", Messages.Word, "answer_3_2"),
        Task("zone2", "task_chain_3_3", Messages.Word, "answer_3_3"),
    ],
]

task_chain_name_to_task_chain_index = query(range(len(task_chains))).to_dictionary(lambda x: Messages.TaskNumber.format(x))


class Team:
    def __init__(self, name, pin):
        self.pin = pin
        self.name = name
        self.time_start = None
        self.time_end = None
        self.progress = [0] * len(task_chains)  # next task index for every chain


class State:
    SELECT_TEAM = 'select_team'
    SELECT_CHAIN = 'select_chain'
    ENTER_ANSWER = 'enter_answer'
    QUEST_COMPLETE = 'quest_complete'


class User:
    def __init__(self, user_id):
        self.id = user_id
        self.team = None
        self.chain_index = None
        self.state = State.SELECT_TEAM

    def __get_task(self):
        assert self.team is not None
        assert self.chain_index is not None
        return task_chains[self.chain_index][self.team.progress[self.chain_index]]

    def __handle_select_team(self, input):
        team = teams.get(input)

        if team is not None:
            self.team = team
            bot.send_message(self.id, Messages.Welcome.format(team.name))
            return self.__handle_select_chain(None)

        bot.send_message(self.id, Messages.EnterPin)
        return State.SELECT_TEAM

    def __get_task_markup(self):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton(Messages.ReplyTask))
        markup.add(types.KeyboardButton(Messages.Back))
        return markup

    def __handle_select_chain(self, input):
        assert self.team is not None

        chain_index = task_chain_name_to_task_chain_index.get(input)

        if chain_index is not None:
            self.chain_index = chain_index
            bot.send_message(self.id, Messages.TaskNumber.format(self.chain_index))
            bot.send_message(self.id, str(self.__get_task()), reply_markup=self.__get_task_markup())
            return State.ENTER_ANSWER

        chain_buttons = query(range(len(task_chains))
            ).where(lambda i: self.team.progress[i] < len(task_chains[i])
            ).select(lambda i: types.KeyboardButton(Messages.TaskNumber.format(i + 1))
            ).to_list()

        if len(chain_buttons) == 0:
            return self.__handle_quest_complete()

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(*chain_buttons)
        bot.send_message(self.id, Messages.SelectTask, reply_markup=markup)
        return State.SELECT_CHAIN

    def __handle_enter_answer(self, input):
        assert self.team is not None
        assert self.chain_index is not None

        # current chain is done, dropping user to chain selection
        if self.team.progress[self.chain_index] == len(task_chains[self.chain_index]):
            bot.send_message(self.id, Messages.TaskDone.format(self.chain_index))
            self.chain_index = None
            return self.__handle_select_chain(None)

        task = self.__get_task()

        if input == Messages.ReplyTask:
            bot.send_message(self.id, str(task), reply_markup=self.__get_task_markup())
            return State.ENTER_ANSWER

        if input == Messages.Back:
            return self.__handle_select_chain(None)

        if input.lower() in task.answers:
            bot.send_message(self.id, Messages.CorrectAnswer)
            self.team.progress[self.chain_index] += 1
            return self.__handle_enter_answer(Messages.ReplyTask)

        bot.send_message(self.id, Messages.WrongAnswer, reply_markup=self.__get_task_markup())
        return State.ENTER_ANSWER

    def __handle_quest_complete(self):
        assert self.team is not None

        if self.team.time_end is None:
            self.team.time_end = datetime.now()

        bot.send_message(self.id, Messages.QuestComplete.format(self.team.time_end - self.team.time_start))
        return State.QUEST_COMPLETE

    def handle(self, message):
        assert message.chat.id == self.id

        if self.state == State.SELECT_TEAM:
            self.state = self.__handle_select_team(message.text)

        elif self.state == State.QUEST_COMPLETE:
            self.state = self.__handle_quest_complete()

        elif self.state == State.SELECT_CHAIN:
            self.state = self.__handle_select_chain(message.text)

        elif self.state == State.ENTER_ANSWER:
            self.state = self.__handle_enter_answer(message.text)

        if self.state == State.ENTER_ANSWER and self.team.time_start is None:
            self.team.time_start = datetime.now()


state_file_name = './state.json'

default_teams = [
    Team('team1', 'pin1'),
    Team('team2', 'pin2'),
    Team('team3', 'pin3'),
    Team('team4', 'pin4'),
    Team('team5', 'pin5'),
]

teams = {}
users = {}

try:
    state = None

    with open(state_file_name, 'r') as file:
        state = json.load(file)

    for state_team in state['teams']:
        team = Team(state_team['name'], state_team['pin'])
        team.time_start = datetime.strptime(state_team['time_start'], time_format) if state_team['time_start'] is not None else None
        team.time_end = datetime.strptime(state_team['time_end'], time_format) if state_team['time_end'] is not None else None
        team.progress = state_team['progress']

        teams[team.pin] = team

    for state_user in state['users']:
        user = User(state_user['id'])
        user.team = teams[state_user['team_pin']] if state_user['team_pin'] is not None else None
        user.chain_index = state_user['chain_index']
        user.state = state_user['state']

        users[user.id] = user

except Exception as e:
    print(e)
    teams = {team.pin: team for team in default_teams}
    users = {}


bot = telebot.TeleBot(token=Token)


@bot.message_handler(commands=['start'])
def handle_start(message):
    users[message.chat.id] = None
    handle_message(message)


@bot.message_handler(content_types=['text'])
def handle_message(message):
    user = users.get(message.chat.id)

    if user is None:
        user = User(message.chat.id)
        users[user.id] = user

    user.handle(message)

    store_teams = query(teams.values()
        ).select(lambda t: {
            'name': t.name,
            'time_start': t.time_start.strftime(time_format) if t.time_start is not None else None,
            'time_end': t.time_end.strftime(time_format) if t.time_end is not None else None,
            'progress': t.progress,
            'pin': t.pin
        }).to_list()

    store_users = query(users.values()
        ).select(lambda u: {
            'id': u.id,
            'team_pin': u.team.pin if u.team is not None else None,
            'chain_index': u.chain_index, 'state': u.state
        }).to_list()

    state = {'teams': store_teams, 'users': store_users}

    with open(state_file_name, 'w') as file:
        json.dump(state, file, indent=4)


bot.infinity_polling()
