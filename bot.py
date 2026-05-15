import logging

from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatAction
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config import configure_logging, get_settings
from llm import LLMService
from storage import EntryStorage

configure_logging()
logger = logging.getLogger(__name__)

settings = get_settings()
bot = Bot(token=settings.telegram_bot_token)
dp = Dispatcher()
router = Router()
llm_service = LLMService()
entry_storage = EntryStorage()


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(
        "Привет. Можешь отправить мне голосовое сообщение о том, как ты себя чувствуешь. "
        "Я расшифрую его, выделю мягкие метрики самонаблюдения и отвечу короткой рефлексией. "
        "Это не медицинский инструмент и не замена врачу."
    )


@router.message(F.voice)
async def handle_voice(message: Message) -> None:
    if not message.voice or not message.from_user:
        await message.answer("Не получилось прочитать голосовое сообщение. Попробуй отправить его ещё раз.")
        return

    user = message.from_user
    logger.info("Voice message received: user_id=%s duration=%s", user.id, message.voice.duration)

    try:
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        status_message = await message.answer("расшифровываю голосовое")

        file = await message.bot.get_file(message.voice.file_id)
        audio_buffer = await message.bot.download_file(file.file_path)
        audio_bytes = audio_buffer.read()

        transcript = await llm_service.transcribe_voice(audio_bytes, filename="voice.ogg")

        await status_message.edit_text("анализирую состояние")
        metrics = await llm_service.analyze_transcript(transcript)

        await status_message.edit_text("сохраняю запись")
        await entry_storage.append_entry(
            user_id=user.id,
            username=user.username,
            transcript=transcript,
            metrics=metrics,
        )

        reflection = await llm_service.write_reflection(transcript, metrics)
        await status_message.delete()
        await message.answer(reflection)

    except Exception as exc:
        logger.exception("Voice processing failed for user_id=%s: %s", user.id, exc)
        await message.answer(
            "Сейчас не получилось обработать голосовое. Данные могли не сохраниться. "
            "Попробуй ещё раз чуть позже. Если тебе небезопасно или есть риск навредить себе, "
            "пожалуйста, сразу обратись в экстренные службы, к врачу или к близкому человеку."
        )


@router.message()
async def handle_other_messages(message: Message) -> None:
    await message.answer("Пока MVP работает с голосовыми сообщениями. Отправь voice message, и я его обработаю.")


async def on_startup() -> None:
    logger.info("Setting Telegram webhook: %s", settings.webhook_url)
    await bot.set_webhook(settings.webhook_url)


async def on_shutdown() -> None:
    logger.info("Deleting Telegram webhook and closing bot session")
    await bot.delete_webhook(drop_pending_updates=False)
    await bot.session.close()


async def health_check(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def create_app() -> web.Application:
    dp.include_router(router)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    app.router.add_get("/health", health_check)
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=settings.webhook_path)
    setup_application(app, dp, bot=bot)
    return app


app = create_app()


if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=settings.port)
