"""
WebSocket 라우터

배치 수집 진행 상황을 실시간으로 전송
"""

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


class ConnectionManager:
    """WebSocket 연결 관리자"""

    def __init__(self):
        self.active_connections: dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, batch_id: str):
        """클라이언트 연결"""
        await websocket.accept()
        if batch_id not in self.active_connections:
            self.active_connections[batch_id] = set()
        self.active_connections[batch_id].add(websocket)
        logger.info(f"WebSocket 연결: batch_id={batch_id}, 총 {len(self.active_connections[batch_id])}개 연결")

    def disconnect(self, websocket: WebSocket, batch_id: str):
        """클라이언트 연결 해제"""
        if batch_id in self.active_connections:
            self.active_connections[batch_id].discard(websocket)
            if not self.active_connections[batch_id]:
                del self.active_connections[batch_id]
        logger.info(f"WebSocket 연결 해제: batch_id={batch_id}")

    async def broadcast(self, batch_id: str, message: dict):
        """특정 배치를 구독하는 모든 클라이언트에게 메시지 전송"""
        if batch_id not in self.active_connections:
            return

        # 동시성 문제 방지: 복사본으로 순회
        connections = list(self.active_connections[batch_id])
        disconnected = set()

        for connection in connections:
            try:
                await connection.send_json(message)
            except WebSocketDisconnect:
                logger.warning(f"WebSocket 연결 끊김: batch_id={batch_id}")
                disconnected.add(connection)
            except Exception as e:
                logger.error(f"메시지 전송 실패: {e}", exc_info=True)
                disconnected.add(connection)

        # 연결이 끊어진 클라이언트 제거
        for conn in disconnected:
            self.active_connections[batch_id].discard(conn)

        # 배치에 연결된 클라이언트가 없으면 딕셔너리에서 제거 (메모리 누수 방지)
        if batch_id in self.active_connections and not self.active_connections[batch_id]:
            del self.active_connections[batch_id]
            logger.debug(f"배치 {batch_id}의 모든 연결 제거됨")


manager = ConnectionManager()


@router.websocket("/batch/{batch_id}")
async def batch_websocket(websocket: WebSocket, batch_id: str):
    """
    배치 수집 진행 상황 WebSocket

    Args:
        batch_id: 배치 ID

    연결되면 배치 상태 변경 시 실시간으로 데이터 전송
    """
    await manager.connect(websocket, batch_id)
    try:
        # 연결 유지 (클라이언트가 연결 해제할 때까지)
        while True:
            # 클라이언트로부터 메시지 수신 (ping/pong 등)
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, batch_id)
        logger.info(f"클라이언트 연결 해제: batch_id={batch_id}")
    except Exception as e:
        logger.error(f"WebSocket 오류: {e}")
        manager.disconnect(websocket, batch_id)
