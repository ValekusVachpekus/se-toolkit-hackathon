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
