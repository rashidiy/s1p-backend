import os

from aiogram.enums import ParseMode
from mako.template import Template

from api.v1.schemas import SipuniEventSchema
from core.config import BASE_DIR, tg_bot
from db.models import Sipuni
from db.models.enums import CallStatusEnum
from utils.services import SipuniApiSimulator as SaS
from utils.validators import validate_phone_number


def escape_md(text: str) -> str:
    escape_chars = r"_*[]()~`>#+-=|{}.!\\"
    return ''.join(f'\\{c}' if c in escape_chars else c for c in text)


class Broadcast:
    template_file_dir = os.path.join(BASE_DIR, 'source/api/v1/routers/sipuni/stream/templates/')
    operators = {}

    def __init__(self, sipuni: Sipuni, event: SipuniEventSchema.HangupEvent, lang: str = 'en'):
        self.sipuni = sipuni
        self.event = event
        self.lang = lang

    def get_successful_call_context(self) -> dict:
        return {
            'call_record_link': escape_md(self.event.record_link),
            'subscriber': escape_md(self.event.pbxdstnum),
            'operator_id': escape_md(self.event.short_src_num),
            'operator_name': escape_md(self.operators.get(self.event.short_src_num)['name']),
        }

    def get_failed_call_context(self) -> dict:
        return {
            'subscriber': escape_md(self.event.pbxdstnum),
            'operator_id': escape_md(self.event.short_src_num),
            'operator_name': escape_md(self.operators.get(self.event.short_src_num)['name']),
        }

    def get_operator_accept_context(self) -> dict:
        return {
            'call_record_link': escape_md(self.event.record_link),
            'operator_id': escape_md(self.event.last_called[-1]),
            'operator_name': escape_md(self.operators.get(self.event.last_called[-1])['name']),
            'subscriber': escape_md('+' + validate_phone_number(self.event.short_src_num)),
            'tree_name': escape_md(self.event.tree_name),
        }

    def get_operator_not_found_context(self) -> dict:
        print(self.event.model_dump())
        return {}

    def get_template(self) -> tuple[str, dict]:
        a = {
            ('1', '2', CallStatusEnum.ANSWER): 'successful_call',
            ('1', '2', CallStatusEnum.NOANSWER): 'failed_call',
            ('1', '1', CallStatusEnum.ANSWER): 'operator_accept',
            ('1', '1', CallStatusEnum.NOANSWER): 'operator_not_found',
        }
        template_file = a.get((self.event.dst_type, self.event.src_type, self.event.status))
        return f'{self.template_file_dir}/{template_file}.mako', getattr(self, f'get_{template_file}_context')()

    async def broadcast(self):
        self.operators = await SaS.get_operators_json(user=self.sipuni.cabinet_id, secret=self.sipuni.security_key)
        temp_file, context = self.get_template()
        text = Template(filename=temp_file).render(**context)
        await tg_bot.send_message(1825715682, text, parse_mode=ParseMode.MARKDOWN_V2)
