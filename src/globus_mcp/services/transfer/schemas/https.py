from typing import Literal

from pydantic import BaseModel, Field


class HttpsUploadResponse(BaseModel):
    url: str = Field(description="URL of the file on the collection")
    path: str = Field(description="Path of the file on the collection")


class HttpsDownloadResponse(BaseModel):
    content: str = Field(
        description="File content, encoded as specified by the 'encoding' field"
    )
    encoding: Literal["utf-8", "base64"] = Field(
        description="Content encoding: 'utf-8' for text files, 'base64' for binary files"
    )
    size_bytes: int = Field(description="Size of the file content in bytes")
    url: str = Field(description="URL the file was downloaded from")


class HttpsFileUploadResponse(BaseModel):
    url: str = Field(description="URL of the file on the collection")
    collection_path: str = Field(description="Path of the file on the collection")
    local_path: str = Field(description="Absolute local path the file was read from")
    size_bytes: int = Field(description="Size of the uploaded file in bytes")


class HttpsFileDownloadResponse(BaseModel):
    url: str = Field(description="URL the file was downloaded from")
    collection_path: str = Field(description="Path of the file on the collection")
    local_path: str = Field(description="Absolute local path the file was saved to")
    size_bytes: int = Field(description="Size of the downloaded file in bytes")
