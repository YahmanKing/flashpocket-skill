# 架空の会話（conversation モードの Eval 用）

人が期待候補と突き合わせる Manual 用。自動採点はしない。

## 会話

**User:** 「認識を合わせる」って英語で何て言う？
**AI:** "get on the same page" が自然です。
**User:** I will check it with him and back to you tomorrow.
**AI:** "I'll check with him and get back to you tomorrow." がより自然です。
**User:** "circle back" ってどういう意味？
**AI:** 「後で改めて話を戻す」という意味です。
**User:** それ、使いたいな。ところで今日の天気はどう？
**AI:** 晴れです。Python のバージョンは 3.12 を使っています。

## 期待する候補

| 合図 | meaning | chunk |
|---|---|---|
| 1 言い方を尋ねた | 認識を合わせる | get on the same page |
| 2 直された | 後で連絡する | get back to you |
| 3 意味を尋ねた・4 使いたい | 後で改めて話を戻す | circle back |

## 拾わない

- 天気、Python、バージョン番号などの雑談・話題そのもの
- "today"、"check" のような一般的すぎる語

## 例文の確認

`example` は自分の言葉で書かれ、上の会話の文面と一致しない。
