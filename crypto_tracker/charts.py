from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


def render_chart(symbol: str, points: list[tuple[float, float]]) -> BytesIO:
    width, height, pad = 1280, 720, 92
    image = Image.new("RGB", (width, height), "#10131c")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 38)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    prices = [price for _, price in points]
    low, high = min(prices), max(prices)
    span = max(high - low, high * 0.001)
    for index in range(5):
        y = pad + index * (height - pad * 2) / 4
        draw.line((pad, y, width - pad, y), fill="#252b3b", width=2)
    coords = []
    for index, price in enumerate(prices):
        x = pad + index * (width - pad * 2) / max(1, len(prices) - 1)
        y = height - pad - (price - low) / span * (height - pad * 2)
        coords.append((x, y))
    rising = prices[-1] >= prices[0]
    color = "#35d0a0" if rising else "#ff6685"
    draw.line(coords, fill=color, width=6, joint="curve")
    draw.text((pad, 30), f"{symbol} · 24 часа", fill="#f4f6fb", font=font)
    draw.text((pad, height - 60), f"Минимум: ${low:,.4f}     Максимум: ${high:,.4f}", fill="#aeb7ca", font=small)
    output = BytesIO()
    output.name = f"{symbol.lower()}-24h.png"
    image.save(output, "PNG")
    output.seek(0)
    return output
