# user_management.py
import streamlit as st
import stripe
import sqlite3
import pandas as pd
import json
from datetime import datetime, timedelta
import hashlib
import uuid
from typing import Dict, List, Optional
import plotly.express as px
import plotly.graph_objects as go

class UserManager:
    def __init__(self):
        self.init_database()
        # Stripe設定
        stripe.api_key = st.secrets.get("stripe_api_key_test", "")
        
    def init_database(self):
        """ユーザーデータベースを初期化"""
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        
        # ユーザーテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                stripe_customer_id TEXT,
                subscription_status TEXT DEFAULT 'inactive',
                subscription_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_admin BOOLEAN DEFAULT FALSE
            )
        ''')
        
        # 使用履歴テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                feature_type TEXT NOT NULL,  -- video, audio, realtime
                file_name TEXT,
                file_size_mb REAL,
                processing_time_seconds REAL,
                characters_processed INTEGER,
                translation_used BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # 管理者ユーザーを作成（初回のみ）
        admin_email = "shion@example.com"  # あなたのメール
        admin_exists = cursor.execute(
            "SELECT id FROM users WHERE email = ? AND is_admin = TRUE",
            (admin_email,)
        ).fetchone()
        
        if not admin_exists:
            admin_password_hash = hashlib.sha256("admin123".encode()).hexdigest()
            cursor.execute('''
                INSERT INTO users (email, password_hash, name, is_admin, subscription_status)
                VALUES (?, ?, ?, TRUE, 'active')
            ''', (admin_email, admin_password_hash, "Shion Shimada"))
            
        conn.commit()
        conn.close()

    def create_user(self, email: str, password: str, name: str) -> Dict:
        """新規ユーザー作成"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            # メール重複チェック
            existing = cursor.execute(
                "SELECT id FROM users WHERE email = ?", (email,)
            ).fetchone()
            
            if existing:
                return {"success": False, "message": "このメールアドレスは既に登録されています"}
            
            # Stripe顧客作成
            stripe_customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata={"app": "subtitle_generator"}
            )
            
            # パスワードハッシュ化
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            # ユーザー作成
            cursor.execute('''
                INSERT INTO users (email, password_hash, name, stripe_customer_id)
                VALUES (?, ?, ?, ?)
            ''', (email, password_hash, name, stripe_customer.id))
            
            user_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return {
                "success": True,
                "message": "ユーザー作成成功",
                "user_id": user_id,
                "stripe_customer_id": stripe_customer.id
            }
            
        except Exception as e:
            return {"success": False, "message": f"エラー: {str(e)}"}

    def authenticate_user(self, email: str, password: str) -> Optional[Dict]:
        """ユーザー認証"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            user = cursor.execute('''
                SELECT id, email, name, stripe_customer_id, subscription_status, is_admin
                FROM users WHERE email = ? AND password_hash = ?
            ''', (email, password_hash)).fetchone()
            
            if user:
                # 最終ログイン時刻更新
                cursor.execute(
                    "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                    (user[0],)
                )
                conn.commit()
                
                return {
                    "id": user[0],
                    "email": user[1],
                    "name": user[2],
                    "stripe_customer_id": user[3],
                    "subscription_status": user[4],
                    "is_admin": bool(user[5])
                }
            
            conn.close()
            return None
            
        except Exception as e:
            st.error(f"認証エラー: {str(e)}")
            return None

    def create_subscription(self, user_id: int, price_id: str) -> Dict:
        """サブスクリプション作成"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            # ユーザー情報取得
            user = cursor.execute(
                "SELECT stripe_customer_id FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            
            if not user:
                return {"success": False, "message": "ユーザーが見つかりません"}
            
            # Stripeサブスクリプション作成
            subscription = stripe.Subscription.create(
                customer=user[0],
                items=[{"price": price_id}],
                payment_behavior="default_incomplete",
                payment_settings={"save_default_payment_method": "on_subscription"},
                expand=["latest_invoice.payment_intent"]
            )
            
            # データベース更新
            cursor.execute('''
                UPDATE users 
                SET subscription_id = ?, subscription_status = ?
                WHERE id = ?
            ''', (subscription.id, subscription.status, user_id))
            
            conn.commit()
            conn.close()
            
            return {
                "success": True,
                "subscription_id": subscription.id,
                "client_secret": subscription.latest_invoice.payment_intent.client_secret
            }
            
        except Exception as e:
            return {"success": False, "message": f"サブスクリプション作成エラー: {str(e)}"}

    def log_usage(self, user_id: int, feature_type: str, **kwargs):
        """使用ログ記録"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO usage_logs 
                (user_id, feature_type, file_name, file_size_mb, processing_time_seconds, 
                 characters_processed, translation_used)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                feature_type,
                kwargs.get('file_name', ''),
                kwargs.get('file_size_mb', 0),
                kwargs.get('processing_time_seconds', 0),
                kwargs.get('characters_processed', 0),
                kwargs.get('translation_used', False)
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            st.warning(f"使用ログ記録エラー: {str(e)}")

    def get_user_usage_stats(self, user_id: int) -> Dict:
        """ユーザー使用統計取得"""
        try:
            conn = sqlite3.connect('users.db')
            
            # 総使用統計
            total_stats = pd.read_sql_query('''
                SELECT 
                    feature_type,
                    COUNT(*) as usage_count,
                    SUM(file_size_mb) as total_file_size_mb,
                    SUM(processing_time_seconds) as total_processing_time,
                    SUM(characters_processed) as total_characters,
                    AVG(file_size_mb) as avg_file_size_mb
                FROM usage_logs 
                WHERE user_id = ?
                GROUP BY feature_type
            ''', conn, params=(user_id,))
            
            # 日別使用統計（過去30日）
            daily_stats = pd.read_sql_query('''
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as daily_usage,
                    SUM(characters_processed) as daily_characters
                FROM usage_logs 
                WHERE user_id = ? AND created_at >= datetime('now', '-30 days')
                GROUP BY DATE(created_at)
                ORDER BY date
            ''', conn, params=(user_id,))
            
            conn.close()
            
            return {
                "total_stats": total_stats,
                "daily_stats": daily_stats
            }
            
        except Exception as e:
            st.error(f"統計取得エラー: {str(e)}")
            return {"total_stats": pd.DataFrame(), "daily_stats": pd.DataFrame()}

    def get_all_users_stats(self) -> Dict:
        """全ユーザー統計（管理者用）"""
        try:
            conn = sqlite3.connect('users.db')
            
            # ユーザー一覧
            users_df = pd.read_sql_query('''
                SELECT 
                    u.id, u.email, u.name, u.subscription_status,
                    u.created_at, u.last_login,
                    COUNT(ul.id) as total_usage,
                    SUM(ul.characters_processed) as total_characters,
                    SUM(ul.file_size_mb) as total_file_size_mb
                FROM users u
                LEFT JOIN usage_logs ul ON u.id = ul.user_id
                WHERE u.is_admin = FALSE
                GROUP BY u.id
                ORDER BY u.created_at DESC
            ''', conn)
            
            # 機能別統計
            feature_stats = pd.read_sql_query('''
                SELECT 
                    feature_type,
                    COUNT(*) as usage_count,
                    COUNT(DISTINCT user_id) as unique_users,
                    SUM(characters_processed) as total_characters,
                    AVG(processing_time_seconds) as avg_processing_time
                FROM usage_logs
                GROUP BY feature_type
            ''', conn)
            
            # 日別統計
            daily_overall = pd.read_sql_query('''
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as daily_usage,
                    COUNT(DISTINCT user_id) as daily_active_users,
                    SUM(characters_processed) as daily_characters
                FROM usage_logs 
                WHERE created_at >= datetime('now', '-30 days')
                GROUP BY DATE(created_at)
                ORDER BY date
            ''', conn)
            
            conn.close()
            
            return {
                "users": users_df,
                "features": feature_stats,
                "daily": daily_overall
            }
            
        except Exception as e:
            st.error(f"全体統計取得エラー: {str(e)}")
            return {"users": pd.DataFrame(), "features": pd.DataFrame(), "daily": pd.DataFrame()}

def render_admin_dashboard():
    """管理者ダッシュボード表示"""
    # 戻るボタンを上部に追加
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("⬅️ メインアプリに戻る", use_container_width=True):
            st.session_state.page = "main"
            st.rerun()
    with col2:
        st.markdown("## 🔧 管理者ダッシュボード")
    
    user_manager = UserManager()
    stats = user_manager.get_all_users_stats()
    
    # メトリクス表示
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_users = len(stats["users"])
        st.metric("総ユーザー数", total_users)
    
    with col2:
        active_users = len(stats["users"][stats["users"]["subscription_status"] == "active"])
        st.metric("アクティブユーザー", active_users)
    
    with col3:
        total_usage = stats["users"]["total_usage"].sum()
        st.metric("総利用回数", total_usage)
    
    with col4:
        total_characters = stats["users"]["total_characters"].sum()
        st.metric("総処理文字数", f"{total_characters:,}")
    
    # ユーザー一覧
    st.markdown("### 👥 ユーザー一覧")
    if not stats["users"].empty:
        # サブスクリプション状態でフィルタリング
        status_filter = st.selectbox(
            "ステータスフィルター",
            ["すべて", "active", "inactive", "canceled"]
        )
        
        filtered_users = stats["users"] if status_filter == "すべて" else \
                        stats["users"][stats["users"]["subscription_status"] == status_filter]
        
        st.dataframe(
            filtered_users[["email", "name", "subscription_status", "total_usage", "total_characters", "last_login"]],
            use_container_width=True
        )
    
    # 機能使用統計
    st.markdown("### 📊 機能使用統計")
    if not stats["features"].empty:
        col1, col2 = st.columns(2)
        
        with col1:
            # 機能別使用回数
            fig_features = px.bar(
                stats["features"],
                x="feature_type",
                y="usage_count",
                title="機能別使用回数",
                labels={"feature_type": "機能", "usage_count": "使用回数"}
            )
            st.plotly_chart(fig_features, use_container_width=True)
        
        with col2:
            # 機能別ユニークユーザー数
            fig_users = px.bar(
                stats["features"],
                x="feature_type",
                y="unique_users",
                title="機能別ユニークユーザー数",
                labels={"feature_type": "機能", "unique_users": "ユニークユーザー"}
            )
            st.plotly_chart(fig_users, use_container_width=True)
    
    # 日別使用統計
    st.markdown("### 📈 日別使用統計（過去30日）")
    if not stats["daily"].empty:
        fig_daily = go.Figure()
        
        fig_daily.add_trace(go.Scatter(
            x=stats["daily"]["date"],
            y=stats["daily"]["daily_usage"],
            mode='lines+markers',
            name='使用回数',
            yaxis='y'
        ))
        
        fig_daily.add_trace(go.Scatter(
            x=stats["daily"]["date"],
            y=stats["daily"]["daily_active_users"],
            mode='lines+markers',
            name='アクティブユーザー',
            yaxis='y2'
        ))
        
        fig_daily.update_layout(
            title="日別使用統計",
            xaxis_title="日付",
            yaxis=dict(title="使用回数", side="left"),
            yaxis2=dict(title="アクティブユーザー", side="right", overlaying="y"),
            hovermode='x unified'
        )
        
        st.plotly_chart(fig_daily, use_container_width=True)

def render_user_dashboard(user_info: Dict):
    """ユーザーダッシュボード表示"""
    # 戻るボタンを上部に追加
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("⬅️ メインアプリに戻る", use_container_width=True):
            st.session_state.page = "main"
            st.rerun()
    with col2:
        st.markdown(f"## 👤 {user_info['name']}さんのダッシュボード")
    
    user_manager = UserManager()
    stats = user_manager.get_user_usage_stats(user_info["id"])
    
    # サブスクリプション状態
    col1, col2 = st.columns([2, 1])
    
    with col1:
        if user_info["subscription_status"] == "active":
            st.success("✅ プレミアムプラン利用中")
        else:
            st.warning("⚠️ 無料プラン（機能制限あり）")
            if st.button("💳 プレミアムプランに登録"):
                st.info("Stripe決済画面に移動します...")
    
    with col2:
        st.metric("アカウント作成", "フレンドプラン")
    
    # 使用統計
    if not stats["total_stats"].empty:
        st.markdown("### 📊 あなたの使用統計")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            total_usage = stats["total_stats"]["usage_count"].sum()
            st.metric("総利用回数", total_usage)
        
        with col2:
            total_chars = stats["total_stats"]["total_characters"].sum()
            st.metric("処理文字数", f"{total_chars:,}")
        
        with col3:
            total_time = stats["total_stats"]["total_processing_time"].sum()
            st.metric("総処理時間", f"{total_time:.1f}秒")
        
        # 機能別使用統計
        st.markdown("#### 機能別使用回数")
        feature_chart = px.pie(
            stats["total_stats"],
            values="usage_count",
            names="feature_type",
            title="機能別使用割合"
        )
        st.plotly_chart(feature_chart, use_container_width=True)
    
    # 使用履歴（過去30日）
    if not stats["daily_stats"].empty:
        st.markdown("### 📈 使用履歴（過去30日）")
        daily_chart = px.line(
            stats["daily_stats"],
            x="date",
            y="daily_usage",
            title="日別使用回数",
            labels={"date": "日付", "daily_usage": "使用回数"}
        )
        st.plotly_chart(daily_chart, use_container_width=True)

# グローバル関数
def initialize_user_management():
    """ユーザー管理システム初期化"""
    if 'user_manager' not in st.session_state:
        st.session_state.user_manager = UserManager()
    
    if 'current_user' not in st.session_state:
        st.session_state.current_user = None

def login_form():
    """ログインフォーム"""
    st.markdown("## 🔐 ログイン")
    
    with st.form("login_form"):
        email = st.text_input("メールアドレス", placeholder="your@email.com")
        password = st.text_input("パスワード", type="password")
        submit = st.form_submit_button("ログイン")
        
        if submit:
            user_manager = UserManager()
            user = user_manager.authenticate_user(email, password)
            
            if user:
                st.session_state.current_user = user
                st.success(f"ようこそ、{user['name']}さん！")
                st.rerun()
            else:
                st.error("メールアドレスまたはパスワードが正しくありません")

def signup_form():
    """新規登録フォーム"""
    st.markdown("## 📝 新規登録")
    
    with st.form("signup_form"):
        name = st.text_input("お名前", placeholder="山田太郎")
        email = st.text_input("メールアドレス", placeholder="your@email.com")
        password = st.text_input("パスワード", type="password")
        password_confirm = st.text_input("パスワード確認", type="password")
        submit = st.form_submit_button("登録")
        
        if submit:
            if password != password_confirm:
                st.error("パスワードが一致しません")
                return
            
            user_manager = UserManager()
            result = user_manager.create_user(email, password, name)
            
            if result["success"]:
                st.success("アカウント作成成功！ログインしてください。")
            else:
                st.error(result["message"])

def logout():
    """ログアウト"""
    st.session_state.current_user = None
    st.rerun()
