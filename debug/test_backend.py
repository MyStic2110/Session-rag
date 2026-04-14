import asyncio
import httpx
import json
import logging
import time
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

BASE_URL = "http://localhost:8000"

async def main():
    async with httpx.AsyncClient() as client:
        # 1. Start Session
        logging.info("Starting session...")
        response = await client.post(f"{BASE_URL}/session/start")
        if response.status_code != 200:
            logging.error(f"Failed to start session: {response.text}")
            return
        
        session_id = response.json()["session_id"]
        logging.info(f"Session started with ID: {session_id}")
        
        # 2. Upload Health Document
        health_path = "health.pdf"
        if os.path.exists(health_path):
            logging.info(f"Uploading real health document from {health_path}...")
            with open(health_path, "rb") as f:
                health_content = f.read()
            files = {'file': ('health.pdf', health_content, 'application/pdf')}
        else:
            logging.info("Uploading dummy health document (place health.pdf in debug folder to use real data)...")
            dummy_health_content = b"Patient is healthy. Blood pressure is normal."
            files = {'file': ('health_test.pdf', dummy_health_content, 'application/pdf')}
        data = {'session_id': session_id, 'doc_type': 'health'}
        response = await client.post(f"{BASE_URL}/upload", data=data, files=files, timeout=60.0)
        if response.status_code != 200:
            logging.error(f"Failed to upload health document: {response.text}")
            return
        logging.info("Health document uploaded successfully.")

        # 3. Upload Policy Document
        policy_path = "policy.pdf"
        if os.path.exists(policy_path):
            logging.info(f"Uploading real policy document from {policy_path}...")
            with open(policy_path, "rb") as f:
                policy_content = f.read()
            files = {'file': ('policy.pdf', policy_content, 'application/pdf')}
        else:
            logging.info("Uploading dummy policy document (place policy.pdf in debug folder to use real data)...")
            dummy_policy_content = b"Standard health insurance policy. Covers basic care."
            files = {'file': ('policy_test.pdf', dummy_policy_content, 'application/pdf')}
        data = {'session_id': session_id, 'doc_type': 'policy'}
        response = await client.post(f"{BASE_URL}/upload", data=data, files=files, timeout=60.0)
        if response.status_code != 200:
            logging.error(f"Failed to upload policy document: {response.text}")
            return
        logging.info("Policy document uploaded successfully.")

        # 4. Stream Analysis
        logging.info("Starting streaming analysis...")
        try:
            async with client.stream("GET", f"{BASE_URL}/analyze/stream/{session_id}", timeout=120.0) as response:
                async for line in response.aiter_lines():
                    if line:
                        logging.info(f"Stream: {line}")
        except Exception as e:
            logging.error(f"Streaming failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
