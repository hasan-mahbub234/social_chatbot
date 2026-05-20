"""Tests for authentication endpoints."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_db
from app.models.user import User
from app.core.security import hash_password


client = TestClient(app)


@pytest.fixture
def user_data():
    return {
        "email": "test@example.com",
        "username": "testuser",
        "password": "securepassword123",
        "full_name": "Test User",
    }


def test_register_user(test_db, user_data):
    """Test user registration."""
    app.dependency_overrides[get_db] = lambda: test_db

    response = client.post("/auth/register", json=user_data)

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == user_data["email"]
    assert data["username"] == user_data["username"]
    assert "hashed_password" not in data

    app.dependency_overrides.clear()


def test_register_duplicate_email(test_db, user_data):
    """Test registration with duplicate email."""
    app.dependency_overrides[get_db] = lambda: test_db

    # Create first user
    client.post("/auth/register", json=user_data)

    # Try to create duplicate
    duplicate_data = user_data.copy()
    duplicate_data["username"] = "different_username"
    response = client.post("/auth/register", json=duplicate_data)

    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]

    app.dependency_overrides.clear()


def test_login_success(test_db, user_data):
    """Test successful login."""
    app.dependency_overrides[get_db] = lambda: test_db

    # Register user
    client.post("/auth/register", json=user_data)

    # Login
    response = client.post(
        "/auth/login",
        json={
            "email": user_data["email"],
            "password": user_data["password"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

    app.dependency_overrides.clear()


def test_login_invalid_password(test_db, user_data):
    """Test login with invalid password."""
    app.dependency_overrides[get_db] = lambda: test_db

    # Register user
    client.post("/auth/register", json=user_data)

    # Try wrong password
    response = client.post(
        "/auth/login",
        json={
            "email": user_data["email"],
            "password": "wrongpassword",
        },
    )

    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]

    app.dependency_overrides.clear()


def test_password_validation(test_db):
    """Test password validation."""
    app.dependency_overrides[get_db] = lambda: test_db

    # Password too short
    response = client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
            "username": "testuser",
            "password": "short",  # Less than 8 characters
            "full_name": "Test User",
        },
    )

    assert response.status_code == 422  # Validation error

    app.dependency_overrides.clear()
