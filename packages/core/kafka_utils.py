"""Kafka utilities for message production and consumption."""
import json
from typing import Dict, Any, Optional, Callable
import time

from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError

from packages.core.config import get_settings
from packages.core.logging_config import setup_logging

logger = setup_logging(__name__)


class KafkaMessageProducer:
    """Kafka message producer."""
    
    def __init__(self, bootstrap_servers: Optional[str] = None):
        """Initialize Kafka producer."""
        settings = get_settings()
        self.bootstrap_servers = bootstrap_servers or settings.kafka_bootstrap_servers
        
        self.producer = KafkaProducer(
            bootstrap_servers=self.bootstrap_servers.split(','),
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
        )
        logger.info(f"Kafka producer initialized: {self.bootstrap_servers}")
    
    def send_message(self, topic: str, message: Dict[str, Any], key: Optional[str] = None):
        """
        Send message to Kafka topic.
        
        Args:
            topic: Topic name
            message: Message payload (will be JSON serialized)
            key: Optional message key
        """
        try:
            future = self.producer.send(topic, value=message, key=key)
            # Wait for send to complete
            record_metadata = future.get(timeout=10)
            logger.info(
                f"Message sent to topic={topic}, partition={record_metadata.partition}, "
                f"offset={record_metadata.offset}"
            )
        except KafkaError as e:
            logger.error(f"Failed to send message to {topic}: {e}")
            raise
    
    def close(self):
        """Close producer."""
        self.producer.close()


class KafkaMessageConsumer:
    """Kafka message consumer."""
    
    def __init__(
        self,
        topics: list,
        group_id: Optional[str] = None,
        bootstrap_servers: Optional[str] = None
    ):
        """
        Initialize Kafka consumer.
        
        Args:
            topics: List of topics to subscribe to
            group_id: Consumer group ID
            bootstrap_servers: Kafka bootstrap servers
        """
        settings = get_settings()
        self.bootstrap_servers = bootstrap_servers or settings.kafka_bootstrap_servers
        self.group_id = group_id or settings.kafka_consumer_group
        
        self.consumer = KafkaConsumer(
            *topics,
            bootstrap_servers=self.bootstrap_servers.split(','),
            group_id=self.group_id,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            key_deserializer=lambda k: k.decode('utf-8') if k else None,
            auto_offset_reset='earliest',
            enable_auto_commit=True,
        )
        logger.info(
            f"Kafka consumer initialized: topics={topics}, group={self.group_id}, "
            f"servers={self.bootstrap_servers}"
        )
    
    def consume(self, handler: Callable[[Dict[str, Any]], None]):
        """
        Consume messages and call handler for each message.
        
        Args:
            handler: Function to call for each message
        """
        logger.info("Starting message consumption...")
        
        try:
            for message in self.consumer:
                try:
                    logger.info(
                        f"Received message: topic={message.topic}, "
                        f"partition={message.partition}, offset={message.offset}"
                    )
                    handler(message.value)
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
                    # Continue processing other messages
        except KeyboardInterrupt:
            logger.info("Consumer interrupted by user")
        finally:
            self.close()
    
    def close(self):
        """Close consumer."""
        self.consumer.close()


# Singleton instances
_producer: Optional[KafkaMessageProducer] = None


def get_kafka_producer() -> KafkaMessageProducer:
    """Get or create singleton Kafka producer."""
    global _producer
    if _producer is None:
        _producer = KafkaMessageProducer()
    return _producer


def send_ingest_event(document_id: str, chunk_profile_id: Optional[str] = None):
    """Send document ingest event."""
    producer = get_kafka_producer()
    settings = get_settings()
    
    message = {
        "document_id": document_id,
        "chunk_profile_id": chunk_profile_id,
        "timestamp": time.time(),
    }
    
    producer.send_message(
        settings.kafka_topic_ingest,
        message,
        key=document_id
    )


def send_reindex_event(
    document_id: str,
    chunk_profile_id: str,
    embedding_model: Optional[str] = None
):
    """Send document reindex event."""
    producer = get_kafka_producer()
    settings = get_settings()
    
    message = {
        "document_id": document_id,
        "chunk_profile_id": chunk_profile_id,
        "embedding_model": embedding_model or settings.embedding_model,
        "timestamp": time.time(),
    }
    
    producer.send_message(
        settings.kafka_topic_reindex,
        message,
        key=document_id
    )
