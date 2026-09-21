import pandas as pd

data = {
    "STT": [1, 2, 3, 4, 5, 6, 7, 8],
    "MPN": [
        "STM32F407VGT6",
        "ESP32-WROOM-32E",
        "ATMEGA328P-AU",
        "AMS1117-3.3",
        "CH340G",
        "LM358DR",
        "0603WAF1002T5E",
        "CL10A106KP8NNNC",
    ],
    "Số lượng mua": [500, 1000, 200, 2000, 500, 800, 5000, 5000],
    "Nhà sản xuất": [
        "STMicroelectronics",
        "Espressif Systems",
        "Microchip",
        "Advanced Monolithic",
        "WCH",
        "Texas Instruments",
        "UniOhm",
        "Samsung",
    ],
    "Mô tả": [
        "MCU 32-bit Cortex-M4",
        "Module Wi-Fi & Bluetooth",
        "MCU 8-bit TQFP-32",
        "LDO Regulator 3.3V SOT-223",
        "USB to UART Bridge",
        "Dual Op-Amp SOIC-8",
        "SMD Resistor 10k 0603",
        "SMD Capacitor 10uF 0603",
    ],
}

df = pd.DataFrame(data)
df.to_excel("sample_bom.xlsx", index=False)
print("Đã tạo file sample_bom.xlsx thành công!")