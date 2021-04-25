from heatshrinkpy.core import decode, encode

with open("foo-8-5.hs", "rb") as f:
    data_encoded = f.read()

with open("foo-8-5.txt", "rb") as f:
    data_decoded = f.read()

data_out = encode(data_decoded, window_sz2=8, lookahead_sz2=5)
data_out2 = decode(data_out, window_sz2=8, lookahead_sz2=5)


print(data_out2)
print(data_decoded)
print(data_encoded == data_out)
print(data_decoded == data_out2)
