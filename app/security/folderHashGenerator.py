from random import randint

def generateRandomHash() -> str:
    symbols = "abcdefghijklmnopqrstuvwsyzABCDEFGHIJKLMNOPQRSTUVWSYZ0123456789"
    randHash = ""
    for i in range(16):
        randIndex = randint(1, 62)
        randHash = randHash + symbols[randIndex - 1]
    return randHash
        