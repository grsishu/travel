import bcrypt
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from app.db import SessionLocal, engine, Base
from app.models import User, Device, KYCRecord, PaymentQuote, Transaction, InAppNotification, ExchangeRateCache, utcnow
from app.services.kyc import encrypt_pan, mask_pan

def get_hash(secret: str) -> str:
    return bcrypt.hashpw(secret.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def seed_database():
    print("Creating all database tables...")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # 1. Seed Admin
        admin = db.query(User).filter(User.email == "admin@travelpay.internal").first()
        if not admin:
            admin = User(
                email="admin@travelpay.internal",
                mobile="+919999900000",
                password_hash=get_hash("Admin@123"),
                full_name="TravelPay Administrator",
                dob="1988-01-01",
                role="ADMIN",
                account_status="ACTIVE",
                activation_step=9,
                wallet_balance_inr=Decimal("0.00"),
                terms_accepted=True,
                fema_declaration_accepted=True
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
            print("✓ Seeded Admin: admin@travelpay.internal / Admin@123")

        # 2. Seed Active Demo User
        demo_user = db.query(User).filter(User.mobile == "+919876543210").first()
        if not demo_user:
            demo_user = User(
                mobile="+919876543210",
                email="demo@travelpay.internal",
                password_hash=get_hash("Demo@123"),
                full_name="Aarav Sharma",
                dob="1995-05-15",
                role="USER",
                account_status="ACTIVE",
                activation_step=9,
                pin_hash=get_hash("123456"),
                biometric_enabled=True,
                wallet_balance_inr=Decimal("25000.00"),
                travel_countries=["TH", "ID", "SG"],
                travel_purpose="TOURISM",
                custom_daily_limit_inr=Decimal("50000.00"),
                custom_txn_limit_inr=Decimal("25000.00"),
                terms_accepted=True,
                fema_declaration_accepted=True,
                created_at=utcnow() - timedelta(days=5),
                updated_at=utcnow()
            )
            db.add(demo_user)
            db.commit()
            db.refresh(demo_user)

            # Bind Demo Device
            device = Device(
                user_id=demo_user.id,
                device_id="DEV-DEMO-MOBILE-01",
                device_name="iPhone 15 Pro",
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
                is_active=True,
                last_active_at=utcnow()
            )
            db.add(device)

            # Bind KYC Record
            pan_raw = "ABCDE1234F"
            kyc = KYCRecord(
                user_id=demo_user.id,
                pan_number_encrypted=encrypt_pan(pan_raw),
                pan_number_masked=mask_pan(pan_raw),
                full_name_on_pan="Aarav Sharma",
                address="42 Indiranagar, Bengaluru, Karnataka, 560038",
                passport_number="Z9876543",
                status="VERIFIED",
                verified_at=utcnow() - timedelta(days=4),
                verified_by="SandboxKycProvider (Auto)"
            )
            db.add(kyc)

            # Past Transactions
            t1 = Transaction(
                id="TOPUP-DEMO-01",
                user_id=demo_user.id,
                txn_type="WALLET_TOPUP",
                status="SETTLED",
                inr_amount=Decimal("30000.00"),
                wallet_deduction_inr=Decimal("-30000.00"),
                gateway_payment_id="pay_demo_topup_123",
                settlement_id="GATEWAY-RZP-30000",
                created_at=utcnow() - timedelta(days=3),
                updated_at=utcnow() - timedelta(days=3)
            )
            db.add(t1)

            q1 = PaymentQuote(
                id="QUOTE-DEMO-01",
                user_id=demo_user.id,
                merchant_name="Siam Paragon Cafe",
                merchant_city="Bangkok",
                merchant_country="TH",
                foreign_currency="THB",
                foreign_amount=Decimal("150.00"),
                exchange_rate=Decimal("0.4100"),
                inr_base_amount=Decimal("365.85"),
                markup_percent=Decimal("2.00"),
                markup_inr=Decimal("7.32"),
                gst_percent=Decimal("18.00"),
                gst_inr=Decimal("1.32"),
                total_inr=Decimal("374.49"),
                expires_at=utcnow() + timedelta(days=365),
                is_used=True,
                created_at=utcnow() - timedelta(days=2)
            )
            db.add(q1)

            t2 = Transaction(
                id="TXN-DEMO-01",
                user_id=demo_user.id,
                quote_id=q1.id,
                txn_type="MERCHANT_PAYMENT",
                status="SETTLED",
                merchant_name="Siam Paragon Cafe",
                merchant_city="Bangkok",
                merchant_country="TH",
                foreign_currency="THB",
                foreign_amount=Decimal("150.00"),
                inr_amount=Decimal("374.49"),
                wallet_deduction_inr=Decimal("374.49"),
                settlement_id="STL-SANDBOX-THB150",
                settlement_provider="sandbox",
                settlement_status="SETTLED",
                created_at=utcnow() - timedelta(days=2),
                updated_at=utcnow() - timedelta(days=2)
            )
            db.add(t2)

            db.commit()
            print("✓ Seeded Active Demo User: +919876543210 (PIN: 123456, Balance: ₹25,000.00)")

        # 3. Seed Fresh Inactive User (for testing onboarding gate)
        inactive_user = db.query(User).filter(User.mobile == "+919876543211").first()
        if not inactive_user:
            inactive_user = User(
                mobile="+919876543211",
                role="USER",
                account_status="INACTIVE",
                activation_step=3,
                wallet_balance_inr=Decimal("0.00")
            )
            db.add(inactive_user)
            db.commit()
            print("✓ Seeded Inactive Test User: +919876543211 (Mid-onboarding Step 3)")

        print("Database seeding completed successfully!")
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()

