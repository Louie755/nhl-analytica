import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("nhl_player_stats.csv")

print(df.columns)  # 컬럼 확인

# 컬럼 이름 맞게 수정 필요
df = df[df["GP"] > 0]
df = df[df["S"] > 0]

df["Goals_per_Game"] = df["G"] / df["GP"]
df["Shots_per_Game"] = df["S"] / df["GP"]
df["Shooting_%"] = df["G"] / df["S"]

df["Impact_Score"] = (df["Goals_per_Game"] * 0.6) + (df["Shots_per_Game"] * 0.4)

top5 = df.sort_values(by="Impact_Score", ascending=False).head(5)
print(top5[["Player", "Impact_Score"]])

plt.scatter(df["Shots_per_Game"], df["Goals_per_Game"])
plt.xlabel("Shots per Game")
plt.ylabel("Goals per Game")
plt.show()