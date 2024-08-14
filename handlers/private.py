import json
import time
from aiohttp import ClientSession, ClientResponse
from aiogram import types, Router, F
from aiogram.filters import CommandStart, Command, or_f, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from datetime import datetime, UTC

from config import API_URL
from keyboards.inline import get_callback_btns

private_router = Router()

current_chat_checklist: dict = {}
current_result: dict = {}

class SearchEmployee(StatesGroup):
    personal_number = State()

class SearchResource(StatesGroup):
    inventory_number = State()

class Inspection(StatesGroup):
    begin_datetime = State()
    end_datetime = State()
    reason = State()

def yesno_btns(id: int, is_word: bool = False) -> dict:
    # "❎"
    # "✅"
    if is_word:
        return {"Да": f"btn_inspection_yesno_{id}_1", "Нет": f"btn_inspection_yesno_{id}_0"}
    return {"✅ Исправно": f"btn_broken_{id}_1", "❌ Неисправно": f"btn_broken_{id}_0"}

async def checkpoint_btns(checkpoints: dict) -> dict:    
    btns = {}
    for chkpnt in checkpoints:
        key = f"{chkpnt.get('name')}"
        btns.update({key: f"checkpoint_id_{chkpnt.id}"})
    return btns

async def input_inventory_number_message(message: types.Message, state: FSMContext) -> None:
    text = "Введите инвентарный номер техники:"
    await message.answer(text)
    await state.set_state(SearchResource.inventory_number)

async def answer_checkpoint(message: types.Message):
    checkpoint: list[dict] = current_chat_checklist.get(message.chat.id)
    text = checkpoint[0].get('name')
    await message.answer(text, reply_markup=get_callback_btns(btns = yesno_btns(checkpoint[0].get('id')), sizes=(2, )))

async def get_next_checkpoint(state: FSMContext, message: types.Message = None, callback: types.CallbackQuery = None):
    if callback:
        message = callback.message
    current_chat_checklist.get(message.chat.id).pop(0)
    if current_chat_checklist.get(message.chat.id):
        await answer_checkpoint(message)
    else:
        current_chat_checklist.pop(message.chat.id)
        employee_id: int = current_result.get(message.chat.id).get('employee_id')
        resource_id: int = current_result.get(message.chat.id).get('resource_id')
        resource_name: str = current_result.get(message.chat.id).get('resource')
        inventory_number: str = current_result.get(message.chat.id).get('inventory_number')
        checkpoint: list[dict] = [list(check.values())[0] for check in current_result.get(message.chat.id).get('checkpoint')]
        async with ClientSession() as api_session:
            async with api_session.post(API_URL+'append_checklist', params={ 'employee_id': employee_id, 'resource_id': resource_id}, data=json.dumps(checkpoint, ensure_ascii=True), headers={'content-type': 'application/json'}) as resp:
                response: ClientResponse = resp
                if response.status == 200:
                    response_text: dict = json.loads(await response.text())
                    text = f"<b>Чек-лист <i>#{response_text.get('number')} от {response_text.get('datetime')}</i> на ресурс {resource_name} ({inventory_number}) создан.</b>"
                else:
                    text = "Ошибка при сохранении чек-листа"
                await message.answer(text)
                time.sleep(0.5)
                await input_inventory_number_message(message, state)

@private_router.message(CommandStart())
async def start_command(message: types.Message, state: FSMContext):
    chat_id: int = message.chat.id
    async with ClientSession() as api_session:
        async with api_session.get(API_URL+'get_employee_by_chat_id', params={ 'chat_id': chat_id }) as resp:
            response: ClientResponse = resp
            if response.status == 200:
                await input_inventory_number_message(message, state)
            else:
                text = "Для работы необходимо пройти авторизацию.\nВведите свой табельный номер:"
                await message.answer(text)
                await state.set_state(SearchEmployee.personal_number)

@private_router.message(StateFilter('*'), or_f(Command("exit"), F.text.lower().casefold() == 'завершить'))
async def cmd_checklist_end(message: types.Message, state: FSMContext):
    current_result.pop(message.chat.id)
    async with ClientSession() as api_session:
        async with api_session.post(API_URL+'delete_chat_id', params={ 'chat_id': message.chat.id }) as resp:
            response: ClientResponse = resp
    text = "✅ Выход из системы выполнен."
    await message.answer(text)
    await state.clear()

@private_router.message(SearchEmployee.personal_number, F.text)
async def cmd_set_personal_number(message: types.Message, state: FSMContext) -> None:
    await state.update_data(personal_number = message.text)
    data = await state.get_data()
    await state.clear()
    async with ClientSession() as api_session:
        async with api_session.get(API_URL+'get_employee_by_personal_number', params={ 'personal_number': data.get('personal_number') }) as resp:
            response: ClientResponse = resp
            match response.status:
                case 204:
                    text = "По введённому табельному номеру данных нет.\nПопробуйте ввести заново."
                    await message.answer(text)
                    await state.set_state(SearchEmployee.personal_number)
                
                case 200:
                    response_text: dict = json.loads(await response.text())
                    async with ClientSession() as api_session:
                        async with api_session.post(API_URL+'append_chat_id', params={ 'chat_id': message.chat.id, 'employee_id': response_text.get('id') }) as resp:
                            response: ClientResponse = resp
                    if response.status == 200:
                        current_result[message.chat.id] = current_result.get(message.chat.id, {})
                        current_result[message.chat.id]['employee_id'] = response_text.get('id')
                        fio: str = f"{response_text.get('last_name')} {response_text.get('first_name')[0]}."
                        if response_text.get('middle_name'):
                            fio = fio + f"{response_text.get('middle_name')[0]}."
                        text = f"✅ Авторизация успешна.\nПользователь {fio}"
                        await message.answer(text)
                        time.sleep(0.5)
                        await input_inventory_number_message(message, state)

@private_router.message(SearchResource.inventory_number, F.text)
async def cmd_set_inventory_number(message: types.Message, state: FSMContext) -> None:
    await state.update_data(inventory_number = message.text)
    data = await state.get_data()
    await state.clear()
    async with ClientSession() as api_session:
        async with api_session.get(API_URL+'get_resource_by_inventory_number', params={ 'inventory_number': data.get('inventory_number') }) as resp:
            response: ClientResponse = resp
            match response.status:
                case 204:
                    text = "По введённому инвентарному номеру данных нет.\nПопробуйте ввести заново."
                    await message.answer(text)
                    await state.set_state(SearchResource.inventory_number)
                
                case 200:
                    response_text: dict = json.loads(await response.text())
                    if response.status == 200:
                        last_checklist_datetime = response_text.get('last_checklist_datetime')
                        current_result[message.chat.id]['resource_id'] = response_text.get('id')
                        current_result[message.chat.id]['resource'] = response_text.get('name')
                        current_result[message.chat.id]['inventory_number'] = response_text.get('inventory_number')
                        text = f"<i><b>Найден ресурс</b></i> с инвентарным номером {response_text.get('inventory_number')}:\n"\
                        f"{response_text.get('name')} ({response_text.get('resource_type')})"
                        if last_checklist_datetime:
                            text += f"\nПоследний чек-лист на ресурс был заполнен <i>{last_checklist_datetime}</i>"
                        await message.answer(text)
                        text = f"Начать заполнение чек-листа?"
                        await message.answer(text, reply_markup=get_callback_btns(btns = yesno_btns(response_text.get('id'), is_word=True), sizes=(2, )))

@private_router.callback_query(StateFilter(None), F.data.startswith('btn_inspection_yesno_'))
async def cmd_inspection_yesno(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data.split('_')
    yesno: int = int(data[-1])
    resource_id: int = int(data[-2])
    match yesno:
        case 0:
            await callback.message.delete()
            await input_inventory_number_message(callback.message, state)
        case 1:
            async with ClientSession() as api_session:
                async with api_session.get(API_URL+'get_checkpoint', params={ 'resource_id': resource_id }) as resp:
                    response: ClientResponse = resp
                    match response.status:
                        case 204:
                            text = "Для этой техники не предусмотрен техосмотр. Укажите другую:"
                            await callback.message.answer(text)
                            await state.set_state(SearchResource.inventory_number)

                        case 200:
                            await state.update_data(begin_datetime = datetime.now(UTC))
                            await callback.message.delete()
                            current_chat_checklist[callback.message.chat.id] = current_chat_checklist.get(callback.message.chat.id, json.loads(await response.text()))
                            await answer_checkpoint(callback.message)

@private_router.callback_query(StateFilter('*'), F.data.startswith('btn_broken_'))
async def cmd_inspection_yesno(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data.split('_')
    checkpoint_id: int = int(data[-2])
    checkpoint_status: int = int(data[-1])
    current_result[callback.message.chat.id].setdefault('checkpoint', [])
    match checkpoint_status:
        case 0:
            current_result[callback.message.chat.id]['checkpoint'].append({ checkpoint_id : { 'checkpoint_id': checkpoint_id, 'description': None } })
            await callback.message.edit_text(f'❌ {callback.message.text}')
            await callback.message.answer('Укажите неисправность')
            await state.set_state(Inspection.reason)
        case 1:
            current_result[callback.message.chat.id]['checkpoint'].append({ checkpoint_id: { 'checkpoint_id': checkpoint_id, 'is_good': 'True' } })
            await callback.message.edit_text(f'✅ {callback.message.text}')
            await get_next_checkpoint(callback=callback, state=state)

@private_router.message(Inspection.reason, F.text)
async def cmd_set_reason(message: types.Message, state: FSMContext) -> None:
    await message.delete()
    checkpoint: dict = current_result.get(message.chat.id).get('checkpoint')[-1]
    checkpoint_id: int = list(checkpoint.keys())[0]
    checkpoint.get(checkpoint_id)['description'] = message.text
    await message.answer(f'Описание неисправности: {message.text}')
    await state.clear()
    await get_next_checkpoint(message=message, state=state)
