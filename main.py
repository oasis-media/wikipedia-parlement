import pandas as pd

# Create some data
data = {
    "country": ["France", "Germany", "Italy"],
    "capital": ["Paris", "Berlin", "Rome"],
    "population": [68000000, 84000000, 59000000]
}

# Convert to DataFrame
df = pd.DataFrame(data)

# Save as JSON
df.to_json("countries.json", orient="records", indent=4)

print("JSON created!")