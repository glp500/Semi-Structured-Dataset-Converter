"""
Central JSON schema definition and related prompt templates.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# JSON Schema for the output, as a string (to embed in prompts)
SCHEMA_JSON = """{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Entity Relationship Schema",
  "description": "A schema for representing hierarchical entities with relationships",
  "type": "object",
  "definitions": {
    "entity": {
      "type": "object",
      "properties": {
        "id": {
          "type": "string",
          "description": "Unique identifier for the entity",
          "pattern": "^[a-zA-Z0-9-_]+$"
        },
        "type": {
          "type": "string",
          "description": "Type/category of the entity"
        },
        "name": {
          "type": "string",
          "description": "Primary name/label of the entity"
        },
        "attributes": {
          "type": "object",
          "description": "Additional properties of the entity",
          "additionalProperties": true
        },
        "relations": {
          "type": "object",
          "description": "Hierarchical relationships",
          "properties": {
            "parent": {
              "type": "string",
              "description": "Reference to parent entity ID"
            },
            "children": {
              "type": "array",
              "items": {
                "type": "string"
              },
              "description": "List of child entity IDs"
            }
          }
        }
      },
      "required": ["id", "type", "name"],
      "additionalProperties": false
    }
  },
  "properties": {
    "entities": {
      "type": "array",
      "items": {
        "$ref": "#/definitions/entity"
      },
      "description": "All extracted entities",
      "minItems": 1
    },
    "relationships": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "source": {
            "type": "string",
            "description": "Source entity ID"
          },
          "target": {
            "type": "string",
            "description": "Target entity ID"
          },
          "type": {
            "type": "string",
            "description": "Type of relationship"
          },
          "properties": {
            "type": "object",
            "description": "Additional properties of the relationship",
            "additionalProperties": true
          }
        },
        "required": ["source", "target", "type"],
        "additionalProperties": false
      },
      "description": "Explicit relationships between entities"
    }
  },
  "required": ["entities"],
  "additionalProperties": false
}"""

# Pydantic models for validating the JSON output against the schema
class RelationsModel(BaseModel):
    parent: Optional[str] = None
    children: Optional[List[str]] = None
    missing: Optional[bool] = None
    class Config:
        extra = "forbid"

class EntityModel(BaseModel):
    id: str = Field(..., pattern=r'^[a-zA-Z0-9-_]+$')
    type: str
    name: str
    attributes: Optional[Dict[str, Any]] = None
    relations: Optional[RelationsModel] = None
    class Config:
        extra = "forbid"

class RelationshipModel(BaseModel):
    source: str
    target: str
    type: str
    properties: Optional[Dict[str, Any]] = None
    class Config:
        extra = "forbid"

class OutputModel(BaseModel):
    entities: List[EntityModel]
    relationships: Optional[List[RelationshipModel]] = None
    class Config:
        extra = "forbid"