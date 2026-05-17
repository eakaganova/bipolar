import logging

from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatAction
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config import configure_logging, get_settings
from dynamics import build_history_context
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


TELEGRAM_MESSAGE_LIMIT = 3900


def split_for_telegram(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text.strip()
    while len(remaining) > limit:
        split_at = remaining.rfind("\n\n", 0, limit)
        if split_at == -1:
            split_at = remaining.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = remaining.rfind(" ", 0, limit)
        if split_at == -1 or split_at < limit // 2:
            split_at = limit

        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    if remaining:
        chunks.append(remaining)
    return chunks


START_TEXT = (
    "\u041f\u0440\u0438\u0432\u0435\u0442. \u041d\u0430\u043f\u0438\u0448\u0438 "
    "\u043c\u043d\u0435 \u043f\u0430\u0440\u0443 \u0444\u0440\u0430\u0437 "
    "\u043e \u0442\u043e\u043c, \u043a\u0430\u043a \u0442\u044b "
    "\u0441\u0435\u0431\u044f \u0447\u0443\u0432\u0441\u0442\u0432\u0443\u0435\u0448\u044c. "
    "\u042f \u043c\u044f\u0433\u043a\u043e \u0432\u044b\u0434\u0435\u043b\u044e "
    "\u043c\u0435\u0442\u0440\u0438\u043a\u0438 \u0441\u0430\u043c\u043e\u043d\u0430\u0431\u043b\u044e\u0434\u0435\u043d\u0438\u044f, "
    "\u0441\u043e\u0445\u0440\u0430\u043d\u044e \u0437\u0430\u043f\u0438\u0441\u044c "
    "\u0438 \u043e\u0442\u0432\u0435\u0447\u0443 \u043a\u043e\u0440\u043e\u0442\u043a\u043e\u0439 "
    "\u0440\u0435\u0444\u043b\u0435\u043a\u0441\u0438\u0435\u0439. "
    "\u042d\u0442\u043e \u043d\u0435 \u043c\u0435\u0434\u0438\u0446\u0438\u043d\u0441\u043a\u0438\u0439 "
    "\u0438\u043d\u0441\u0442\u0440\u0443\u043c\u0435\u043d\u0442 \u0438 "
    "\u043d\u0435 \u0437\u0430\u043c\u0435\u043d\u0430 \u0432\u0440\u0430\u0447\u0443."
)


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(START_TEXT)


@router.message(F.text)
async def handle_text(message: Message) -> None:
    if not message.text or not message.from_user:
        await message.answer("\u041d\u0430\u043f\u0438\u0448\u0438 \u0442\u0435\u043a\u0441\u0442\u043e\u043c, \u043a\u0430\u043a \u0442\u044b \u0441\u0435\u0439\u0447\u0430\u0441.")
        return

    user = message.from_user
    text = message.text.strip()
    if len(text) < 3:
        await message.answer("\u041d\u0430\u043f\u0438\u0448\u0438 \u0447\u0443\u0442\u044c \u043f\u043e\u0434\u0440\u043e\u0431\u043d\u0435\u0435, \u0445\u043e\u0442\u044f \u0431\u044b \u043e\u0434\u043d\u043e-\u0434\u0432\u0430 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u044f.")
        return

    logger.info("Text message received: user_id=%s chars=%s", user.id, len(text))

    try:
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        status_message = await message.answer("\u0430\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u0443\u044e \u0441\u043e\u0441\u0442\u043e\u044f\u043d\u0438\u0435")

        try:
            metrics = await llm_service.analyze_text(text)
        except Exception as analysis_exc:
            logger.exception("Analysis failed for user_id=%s: %s", user.id, analysis_exc)
            await status_message.delete()
            await message.answer(
                "\u041f\u043e \u044d\u0442\u043e\u043c\u0443 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044e "
                "\u043f\u043e\u043a\u0430 \u043d\u0435 \u0445\u0432\u0430\u0442\u0430\u0435\u0442 "
                "\u043d\u0430\u0434\u0451\u0436\u043d\u043e\u0433\u043e \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442\u0430 "
                "\u0434\u043b\u044f \u0430\u043d\u0430\u043b\u0438\u0437\u0430.\n\n"
                "\u0427\u0442\u043e\u0431\u044b \u044f \u0442\u043e\u0447\u043d\u0435\u0435 "
                "\u043e\u0442\u0441\u043b\u0435\u0434\u0438\u043b \u0434\u0438\u043d\u0430\u043c\u0438\u043a\u0443, "
                "\u043d\u0430\u043f\u0438\u0448\u0438 \u0441\u0432\u043e\u0431\u043e\u0434\u043d\u043e "
                "\u043f\u0430\u0440\u0443 \u0441\u0442\u0440\u043e\u043a: \u043a\u0430\u043a "
                "\u0441\u043e \u0441\u043d\u043e\u043c, \u044d\u043d\u0435\u0440\u0433\u0438\u0435\u0439, "
                "\u0442\u0440\u0435\u0432\u043e\u0433\u043e\u0439 \u0438 \u0435\u0441\u0442\u044c "
                "\u043b\u0438 \u0441\u0435\u0439\u0447\u0430\u0441 \u0438\u043c\u043f\u0443\u043b\u044c\u0441 "
                "\u0447\u0442\u043e-\u0442\u043e \u0440\u0435\u0437\u043a\u043e \u043c\u0435\u043d\u044f\u0442\u044c."
            )
            return

        try:
            history = await entry_storage.get_recent_entries(user_id=user.id, limit=100)
            history_context = build_history_context(history, metrics)
        except Exception as history_exc:
            logger.exception("History read failed for user_id=%s: %s", user.id, history_exc)
            history_context = (
                "Previous entries could not be loaded because storage history read failed. "
                "Do not infer long-term dynamics; analyze only the current entry."
            )

        await status_message.edit_text("\u0441\u043e\u0445\u0440\u0430\u043d\u044f\u044e \u0437\u0430\u043f\u0438\u0441\u044c")
        storage_saved = True
        try:
            await entry_storage.append_entry(
                user_id=user.id,
                username=user.username,
                transcript=text,
                metrics=metrics,
            )
        except Exception as storage_exc:
            storage_saved = False
            logger.exception("Storage failed for user_id=%s: %s", user.id, storage_exc)

        reflection = await llm_service.write_reflection(text, metrics, history_context)
        await status_message.delete()
        if not storage_saved:
            reflection = (
                reflection
                + "\n\n"
                + "\u0417\u0430\u043f\u0438\u0441\u044c \u0441\u0435\u0439\u0447\u0430\u0441 "
                + "\u043d\u0435 \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u043b\u0430\u0441\u044c "
                + "\u0438\u0437-\u0437\u0430 \u043e\u0448\u0438\u0431\u043a\u0438 "
                + "\u0445\u0440\u0430\u043d\u0438\u043b\u0438\u0449\u0430, \u043d\u043e "
                + "\u0430\u043d\u0430\u043b\u0438\u0437 \u043f\u043e \u0442\u0435\u043a\u0441\u0442\u0443 "
                + "\u044f \u0441\u0434\u0435\u043b\u0430\u043b."
            )
        for chunk in split_for_telegram(reflection):
            await message.answer(chunk)

    except Exception as exc:
        logger.exception("Text processing failed for user_id=%s: %s", user.id, exc)
        error_text = (
            "\u042f \u0441\u0435\u0439\u0447\u0430\u0441 \u043d\u0435 \u0441\u043c\u043e\u0433 "
            "\u043d\u0430\u0434\u0451\u0436\u043d\u043e \u0441\u043e\u0431\u0440\u0430\u0442\u044c "
            "\u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u0443 \u0438\u0437 "
            "\u0437\u0430\u043f\u0438\u0441\u0438, \u043f\u043e\u044d\u0442\u043e\u043c\u0443 "
            "\u043d\u0435 \u0431\u0443\u0434\u0443 \u0434\u0435\u043b\u0430\u0442\u044c "
            "\u0432\u044b\u0432\u043e\u0434\u044b \u043d\u0430 \u0441\u043b\u0430\u0431\u043e\u043c "
            "\u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442\u0435.\n\n"
            "\u041d\u0430\u043f\u0438\u0448\u0438, \u043f\u043e\u0436\u0430\u043b\u0443\u0439\u0441\u0442\u0430, "
            "\u0435\u0449\u0451 \u043e\u0434\u043d\u0438\u043c \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435\u043c: "
            "\u043a\u0430\u043a \u0441\u043e \u0441\u043d\u043e\u043c, "
            "\u044d\u043d\u0435\u0440\u0433\u0438\u0435\u0439, \u0442\u0440\u0435\u0432\u043e\u0433\u043e\u0439 "
            "\u0438 \u0435\u0441\u0442\u044c \u043b\u0438 \u0438\u043c\u043f\u0443\u043b\u044c\u0441 "
            "\u0447\u0442\u043e-\u0442\u043e \u0440\u0435\u0437\u043a\u043e "
            "\u043c\u0435\u043d\u044f\u0442\u044c. \u042d\u0442\u043e \u043f\u043e\u043c\u043e\u0436\u0435\u0442 "
            "\u0441\u043d\u0430\u0447\u0430\u043b\u0430 \u0443\u0442\u043e\u0447\u043d\u0438\u0442\u044c "
            "\u043a\u0430\u0440\u0442\u0438\u043d\u0443, \u0430 \u043d\u0435 "
            "\u0441\u0442\u0430\u0432\u0438\u0442\u044c \u043e\u0446\u0435\u043d\u043a\u0438 "
            "\u0431\u0435\u0437 \u0434\u0430\u043d\u043d\u044b\u0445."
        )
        if settings.debug_errors:
            error_text += f"\n\nТехническая ошибка: {type(exc).__name__}: {str(exc)[:700]}"
        await message.answer(error_text)


@router.message(F.voice)
async def handle_voice(message: Message) -> None:
    await message.answer(
        "\u041f\u043e\u043a\u0430 \u044f \u0440\u0430\u0431\u043e\u0442\u0430\u044e "
        "\u0442\u043e\u043b\u044c\u043a\u043e \u0441 \u0442\u0435\u043a\u0441\u0442\u043e\u043c. "
        "\u041d\u0430\u043f\u0438\u0448\u0438, \u043a\u0430\u043a \u0442\u044b "
        "\u0441\u0435\u0431\u044f \u0447\u0443\u0432\u0441\u0442\u0432\u0443\u0435\u0448\u044c, "
        "\u043e\u0431\u044b\u0447\u043d\u044b\u043c \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435\u043c."
    )


@router.message()
async def handle_other_messages(message: Message) -> None:
    await message.answer("\u041f\u043e\u043a\u0430 MVP \u043f\u0440\u0438\u043d\u0438\u043c\u0430\u0435\u0442 \u0442\u043e\u043b\u044c\u043a\u043e \u0442\u0435\u043a\u0441\u0442.")


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
