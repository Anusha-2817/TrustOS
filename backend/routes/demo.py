from fastapi import APIRouter
import uuid
import time

router = APIRouter()

# 🧠 Fake in-memory DB
orders = {}


# 🧱 STEP 1: CREATE ORDER
@router.post("/create-order")
def create_order(data: dict):

    order_id = str(uuid.uuid4())
    amount = data["amount"]

    # Simple risk logic for demo
    if amount > 10000:
        flow = "HIGH"
        risk = 75
    elif amount > 3000:
        flow = "MEDIUM"
        risk = 50
    else:
        flow = "LOW"
        risk = 20

    orders[order_id] = {
        "flow": flow,
        "verified": False,
        "created_at": time.time(),
        "deadline": None,
        "issue": False
    }

    return {
        "order_id": order_id,
        "risk": risk,
        "flow": flow
    }


# 💰 STEP 2: PAYMENT
@router.post("/pay")
def pay(data: dict):

    order = orders.get(data["order_id"])

    if not order:
        return {"error": "Invalid order_id"}

    if order["flow"] == "HIGH":
        return {"status": "HELD_IN_WALLET"}

    elif order["flow"] == "MEDIUM":
        return {"status": "AUTHORIZED_NOT_CAPTURED"}

    else:
        return {"status": "PAID_TO_SELLER"}


# 📦 STEP 3: VERIFY / ISSUE REPORT
@router.post("/verify")
def verify(data: dict):

    order = orders.get(data["order_id"])

    if not order:
        return {"error": "Invalid order_id"}

    flow = order["flow"]

    # LOW → no verification needed
    if flow == "LOW":
        return {"verified": "NOT_REQUIRED"}

    # MEDIUM → start timer + optional action
    if flow == "MEDIUM":

        # ⏳ start ultimatum window (10 sec for demo instead of 6 hrs)
        if order["deadline"] is None:
            order["deadline"] = time.time() + 10

        if data.get("issue") == True:
            order["issue"] = True
            return {"status": "ISSUE_REPORTED"}

        return {"status": "WAITING_FOR_USER_ACTION","deadline_in_seconds": 10}

    # HIGH → strict verification
    if flow == "HIGH":
        if data.get("video") == True and data.get("otp") == "1234":
            order["verified"] = True
            return {"verified": True}
        else:
                order["verified"] = False 
        return {
            "verified": False,
            "reason": "VIDEO_AND_VALID_OTP_REQUIRED"
        }
    
    # 📊 DEBUG / DEMO API
@router.get("/order-status/{order_id}")
def order_status(order_id: str):

    order = orders.get(order_id)

    if not order:
        return {"error": "Invalid order_id"}

    return {
    "flow": order["flow"],
    "verified": order["verified"],
    "issue": order["issue"],
    "time_left": order["deadline"] - time.time() if order["deadline"] else None
}
#FAST FORWARD TIME (for demo purposes only) ⏲️
@router.post("/fast-forward")
def fast_forward(data: dict):

    order = orders.get(data["order_id"])

    if not order:
        return {"error": "Invalid order_id"}

    # force deadline to past
    order["deadline"] = time.time() - 1

    return {"status": "TIME_FAST_FORWARDED"}

# 🧾 STEP 4: SETTLEMENT
@router.post("/settle")
def settle(data: dict):

    order = orders.get(data["order_id"])

    if not order:
        return {"error": "Invalid order_id"}

    flow = order["flow"]
    verified = order.get("verified", False)
    issue = order.get("issue", False)
    deadline = order.get("deadline")

    now = time.time()

    # 🟢 LOW
    if flow == "LOW":
        return {"result": "PAID_TO_SELLER"}

    # 🟡 MEDIUM
    if flow == "MEDIUM":

        if issue:
            return {"result": "PAYMENT_BLOCKED_DUE_TO_ISSUE"}

        if deadline and now > deadline:
            return {"result": "AUTO_CAPTURED (NO RESPONSE)"}

        return {"result": "WAITING_FOR_USER"}

    # 🔴 HIGH
    if flow == "HIGH":

        if verified:
            return {"result": "RELEASED_TO_SELLER"}

        return {"result": "HOLD - VERIFICATION REQUIRED"}