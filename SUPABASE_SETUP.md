# Supabase Setup

Streamlit Cloudで成績を消さずに使う場合は、ユーザー情報と履歴をSupabaseへ保存します。

## 1. Supabaseプロジェクトを作る

1. Supabaseにログインします。
2. New projectを作成します。
3. Project URLとAPI keyをあとで使います。

## 2. テーブルを作る

SupabaseのSQL Editorで、`supabase_schema.sql` の中身を実行します。

作成されるテーブルは3つです。

- `toeic_users`: ユーザー名とPIN確認用データ
- `toeic_history`: 解答履歴と復習予定日
- `toeic_user_settings`: ユーザーごとの最後に選んだレベル設定

## 3. Streamlit CloudにSecretsを入れる

Streamlit Cloudのアプリ設定で、Secretsに以下を追加します。

```toml
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_KEY = "your-supabase-key"
```

個人利用ならSupabaseのservice role keyでも動かせます。公開範囲が広い場合は、キーの扱いと権限設計を見直してください。

## 4. アプリを再起動する

Secretsを保存したら、Streamlit Cloudでアプリを再起動します。

アプリのサイドバーに `保存先: Supabase` と表示されれば設定完了です。
`保存先: CSV` のままなら、Secrets名または値を確認してください。

## ローカルで試す場合

ローカルでは環境変数でも設定できます。

```bash
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_KEY="your-supabase-key"
streamlit run app.py
```

設定しない場合はCSV保存で動きます。
