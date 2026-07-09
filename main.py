import os
import io
import logging
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from PIL import Image, ImageDraw, ImageFont
from colorthief import ColorThief

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def rgb_to_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*rgb)

def luminance(r, g, b):
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255

def generate_palette_image(colors):
    n = len(colors)
    swatch_w = 130
    swatch_h = 100
    pad = 10
    label_h = 26

    total_w = n * swatch_w + (n + 1) * pad
    total_h = swatch_h + label_h + 3 * pad

    img = Image.new("RGB", (total_w, total_h), (18, 18, 18))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14)
    except Exception:
        font = ImageFont.load_default()

    for i, color in enumerate(colors):
        x = pad + i * (swatch_w + pad)
        y = pad

        draw.rectangle([x, y, x + swatch_w - 1, y + swatch_h - 1], fill=color)
        draw.rectangle([x, y, x + swatch_w - 1, y + swatch_h - 1], outline=(50, 50, 50), width=1)

        hex_code = rgb_to_hex(color)
        label_y = y + swatch_h - label_h
        draw.rectangle(
            [x, label_y, x + swatch_w - 1, y + swatch_h - 1],
            fill=(int(color[0]*0.7), int(color[1]*0.7), int(color[2]*0.7))
        )
        bbox = draw.textbbox((0, 0), hex_code, font=font)
        text_w = bbox[2] - bbox[0]
        draw.text(
            (x + (swatch_w - text_w) // 2, label_y + 5),
            hex_code, fill=(240, 240, 240), font=font
        )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎨 *Color Palette Extractor Bot*\n\n"
        "Send me any photo and I'll extract the dominant colors!\n\n"
        "You'll receive:\n"
        "  • A visual palette preview image\n"
        "  • HEX codes for every color\n"
        "  • RGB values\n\n"
        "By default I extract *6 colors*. You can change it:\n"
        "`/palette 8` — extract 8 colors (max 10)\n\n"
        "Just send a photo to get started! 👇"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *How to use this bot*\n\n"
        "1. Send any photo\n"
        "2. Get the dominant color palette!\n\n"
        "*Commands:*\n"
        "/start — Welcome message\n"
        "/palette `<n>` — Set number of colors (1–10)\n"
        "/help — Show this message"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def set_palette_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        n = int(context.args[0])
        n = max(1, min(10, n))
        context.user_data["color_count"] = n
        await update.message.reply_text(
            f"✅ Got it! I'll extract *{n} colors* from your next photo.",
            parse_mode="Markdown"
        )
    except (IndexError, ValueError):
        await update.message.reply_text(
            "❗ Usage: `/palette <number>` — e.g. `/palette 8`",
            parse_mode="Markdown"
        )


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    color_count = context.user_data.get("color_count", 6)
    processing_msg = await update.message.reply_text("🔍 Extracting colors…")

    try:
        if update.message.photo:
            photo = update.message.photo[-1]
        elif update.message.document:
            photo = update.message.document
        else:
            await processing_msg.edit_text("❌ Please send a photo or image file.")
            return

        file = await context.bot.get_file(photo.file_id)
        buf = io.BytesIO()
        await file.download_to_memory(buf)
        buf.seek(0)

        ct = ColorThief(buf)
        if color_count == 1:
            palette = [ct.get_color(quality=1)]
        else:
            palette = ct.get_palette(color_count=color_count, quality=1)

        palette_img = generate_palette_image(palette)

        lines = ["🎨 *Extracted Palette*\n"]
        for color in palette:
            hex_code = rgb_to_hex(color)
            lines.append(f"`{hex_code}`  —  RGB({color[0]}, {color[1]}, {color[2]})")
        caption = "\n".join(lines)

        await processing_msg.delete()
        await update.message.reply_photo(
            photo=palette_img,
            caption=caption,
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error processing image: {e}", exc_info=True)
        await processing_msg.edit_text(
            "❌ Couldn't process this image. Please send a valid JPEG/PNG photo."
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📷 Send me a photo to extract its color palette!")


async def post_init(application: Application):
    await application.bot.delete_webhook(drop_pending_updates=True)
    await application.bot.set_my_commands([
        BotCommand("start",   "Welcome message"),
        BotCommand("palette", "Set number of colors to extract (1–10)"),
        BotCommand("help",    "How to use the bot"),
    ])


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set!")

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("help",    help_command))
    app.add_handler(CommandHandler("palette", set_palette_count))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot is running…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
