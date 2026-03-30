# Copyright (C) 2026 Shchetkov Ilia
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from aiogram.fsm.state import State, StatesGroup


class ComplaintForm(StatesGroup):
    fio = State()
    address = State()
    description = State()
    media = State()


class EmployeeRegisterForm(StatesGroup):
    fio = State()
    position = State()
    area = State()


class AddEmployeeForm(StatesGroup):
    username = State()


class RejectForm(StatesGroup):
    reason = State()


class RatingForm(StatesGroup):
    rating = State()
    review = State()
