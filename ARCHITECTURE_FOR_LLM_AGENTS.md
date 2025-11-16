# Ankineitor Architecture Guide for LLM Agents

## Project Overview for AI Context

**Ankineitor** is a sophisticated Python application that automates the creation of Anki flashcard decks for Chinese language learning. It combines a Streamlit web interface with a comprehensive data processing pipeline that transforms Chinese words into rich multimedia flashcards with translations, pinyin, audio, and AI-generated example sentences.

## System Architecture Context

### High-Level Purpose
This system serves as an **AI-powered language learning automation tool** that:
- Processes Chinese text input through multiple AI transformations
- Generates multimedia content (audio, translations, example sentences)
- Creates structured Anki flashcard decks
- Provides a user-friendly web interface for non-technical users

### Core Value Proposition
The system leverages **Large Language Models (LLMs)** and **text-to-speech AI** to automatically create comprehensive language learning materials, eliminating manual flashcard creation while ensuring high-quality, contextual learning content.

## Technical Architecture Deep Dive

### 1. Application Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Streamlit Web Interface                 │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐ │
│  │ Anki Generator│ Pipeline    │ CSV Merger  │ Word Extract│ │
│  │ Tab         │ Tab         │ Tab         │ Tab         │ │
│  └─────────────┴─────────────┴─────────────┴─────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  Business Logic Layer                       │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐ │
│  │ Deck        │ Pipeline    │ Data Utils  │ Text Extract│ │
│  │ Generator   │ Orchestrator│             │             │ │
│  └─────────────┴─────────────┴─────────────┴─────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  Data Processing Pipeline                   │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐ │
│  │ Pinyin      │ Translation │ Audio       │ LLM         │ │
│  │ Transform   │ Transform   │ Transform   │ Transform   │ │
│  └─────────────┴─────────────┴─────────────┴─────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Data Persistence Layer                   │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐ │
│  │ Pipeline DB │ LLM Cache   │ Audio Files │ Output      │ │
│  │ (SQLite)    │ (SQLite)    │ (File Sys)  │ Files       │ │
│  └─────────────┴─────────────┴─────────────┴─────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 2. AI Integration Points

#### LLM Integration Architecture
- **Primary LLM**: Groq API with Llama 3.3 70B model
- **Use Cases**: 
  - Chinese word meaning generation (English + Spanish)
  - Contextual example sentence creation
  - Structured output parsing with Pydantic models
- **Caching**: SQLite-based caching to minimize API calls and costs

#### Text-to-Speech Integration
- **Service**: Google Text-to-Speech (gTTS)
- **Languages**: Chinese (Mandarin) pronunciation
- **Output**: WAV audio files for Anki cards
- **Caching**: File-based caching in `my_audio_files/` directory

### 3. Security Architecture Context

#### Critical Security Components
```python
# Security Module Structure
src/ankineitor/security/
├── __init__.py          # Security exports
├── exceptions.py        # Custom security exceptions
└── validators.py        # Input validation functions
```

#### Security Validation Pipeline
1. **File Upload Security**: Multi-layer validation (size, type, content, filename)
2. **Input Sanitization**: Chinese text processing with injection prevention
3. **Path Traversal Protection**: Filename and path validation
4. **SQL Injection Prevention**: Input sanitization for database operations
5. **API Key Security**: Secure configuration management with environment variables

### 4. Data Flow Architecture

#### Word Processing Pipeline
```
Chinese Text Input → Text Extraction → Word List → Pipeline Processing
                      ↓
Pinyin Generation → Translation → Audio Creation → LLM Processing
                      ↓
Database Caching → Result Aggregation → Anki Deck Generation
```

#### Caching Strategy
- **Pipeline Cache**: SQLite database for processed words (pinyin, translation, audio)
- **LLM Cache**: Separate SQLite database for AI-generated content (meanings, sentences)
- **Audio Cache**: File system caching for generated audio files
- **Cache Keys**: Chinese words as primary keys with metadata timestamps

## Component Architecture for LLM Understanding

### 1. Streamlit Interface Components

#### Tab Architecture
Each tab represents a distinct user workflow:

**Anki Deck Generator Tab** (`app/tabs/anki_tab.py`)
- **Purpose**: Final output generation
- **Key Features**: YAML configuration, file upload, deck customization
- **Security**: File validation, input sanitization, path protection
- **Architecture**: Modular template system with separate YAML configurations

#### Template System Architecture
The Anki tab now uses a modular template system for better organization and maintainability:

```python
# Template Structure
app/tabs/templates/
├── __init__.py                    # Package exports
├── basic_model_templates.py       # Default model templates YAML
├── basic_tag_rules.py            # Default tag rules YAML
├── chinese_pipeline_config.py    # Chinese pipeline setup configuration
├── chinese_pipeline_templates.py # Chinese pipeline model templates YAML
└── chinese_pipeline_tag_rules.py # Chinese pipeline tag rules YAML
```

**Template Modularization Benefits:**
- **Separation of Concerns**: YAML templates are separated from UI logic
- **Reusability**: Templates can be imported and used elsewhere
- **Maintainability**: Each template type has its own dedicated file
- **Scalability**: New template types can be easily added

**Template Usage Pattern:**
```python
from .templates import (
    DEFAULT_MODEL_TEMPLATES_YAML,
    DEFAULT_TAG_RULES_YAML,
    CHINESE_PIPELINE_SETUP
)
```

**Template Categories:**
1. **Basic Templates**: Simple card layouts for general vocabulary
2. **Chinese Pipeline Templates**: Advanced templates with pinyin, multiple meanings, examples, and interactive features
3. **Tag Rules**: Automated tagging systems for card organization

**Pipeline Runner Tab** (`app/tabs/pipeline_tab.py`)
- **Purpose**: Core word processing workflow
- **Key Features**: Transformation selection, word input, category management
- **Security**: Word input validation, processing limits, error handling

**CSV Merger Tab** (`app/tabs/merge_csv_tab.py`)
- **Purpose**: Data preprocessing and consolidation
- **Key Features**: Multi-file merging, frequency aggregation
- **Security**: File validation, data integrity checks

**Word Extractor Tab** (`app/tabs/word_extractor_tab.py`)
- **Purpose**: Text preprocessing and word extraction
- **Key Features**: Document parsing, HSK filtering, frequency analysis
- **Security**: File type validation, content sanitization

### 2. Core Processing Components

#### Transformation Pipeline (`src/ankineitor/pipeline/pipeline.py`)
```python
class TransformationPipeline:
    """Orchestrates multiple AI transformations with caching"""
    
    def transform_data(self, words: List[str]) -> pd.DataFrame:
        """Process words through transformation pipeline with caching"""
        # 1. Check cache for existing processed words
        # 2. Process new words through selected transformations
        # 3. Cache results for future use
        # 4. Apply LLM transformations to complete dataset
        # 5. Return merged results with original order preserved
```

#### Individual Transformations
Each transformation implements a standard interface:
```python
class Transformation(ABC):
    @property
    @abstractmethod
    def column_name(self) -> str:
        """Name of the column this transformation creates"""
    
    @abstractmethod
    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply transformation to DataFrame and return updated DataFrame"""
```

### 3. Security Components Architecture

#### Configuration Security (`src/ankineitor/config/settings.py`)
```python
class Settings(BaseSettings):
    """Secure configuration management with validation"""
    groq_api_key: Optional[str] = None  # Validated API key format
    max_file_size_mb: int = 10          # File size limits
    allowed_file_extensions: list = [...]  # File type restrictions
    # Additional security-focused settings...
```

#### Input Validation (`src/ankineitor/security/validators.py`)
```python
def validate_file_upload(file_obj, expected_extensions: List[str] = None) -> bool:
    """Multi-layer file validation: size, type, content, filename"""
    
def validate_word_input(words: Union[str, List[str]]) -> List[str]:
    """Chinese word input validation with security checks"""
    
def sanitize_filename(filename: str) -> str:
    """Filename sanitization preventing path traversal attacks"""
```

## AI/ML Integration Context

### 1. LLM Usage Patterns

#### Structured Output Generation
```python
# Pydantic models for reliable LLM output parsing
class WordMeaning(BaseModel):
    english: str = Field(description="The meaning of the word in English")
    spanish: str = Field(description="The meaning of the word in Spanish")

class ExampleSentences(BaseModel):
    sentence_1: str = Field(description="The first example sentence")
    sentence_2: str = Field(description="The second example sentence") 
    sentence_3: str = Field(description="The third example sentence")
```

#### Prompt Engineering Strategy
- **Language-Specific Prompts**: Chinese prompts for Chinese word processing
- **Structured Output Requirements**: Explicit JSON format specifications
- **Context Preservation**: Maintaining word context in example sentences
- **Quality Control**: Multiple example generation for comprehensive learning

### 2. Caching and Cost Optimization

#### Intelligent Caching Strategy
```python
# Two-tier caching system
1. Pipeline Cache: Stores basic transformations (pinyin, translation, audio)
2. LLM Cache: Stores AI-generated content (meanings, sentences)

# Cache key design: Chinese word + transformation type + metadata
cache_key = f"{word}:{transformation_type}:{language_pair}"
```

#### Cost Management
- **API Call Minimization**: Comprehensive caching reduces LLM API costs
- **Batch Processing**: Efficient processing of word lists
- **Retry Logic**: Exponential backoff for failed API calls
- **Error Handling**: Graceful degradation when AI services are unavailable

## Security Architecture Context

### 1. Threat Model for LLM Agents

#### Primary Security Concerns
1. **Input Injection**: Malicious file uploads or text input
2. **Path Traversal**: Directory traversal through filename manipulation  
3. **Resource Exhaustion**: DoS attacks through large file uploads
4. **API Key Exposure**: Hardcoded or leaked API credentials
5. **Data Poisoning**: Corrupted training data or cache manipulation

#### Security Controls Implemented
```python
# Multi-layer security validation
Layer 1: File size and type validation
Layer 2: Content validation and sanitization  
Layer 3: Filename sanitization and path validation
Layer 4: Input validation and injection prevention
Layer 5: Secure configuration management
```

### 2. Security Validation Pipeline

#### File Upload Security Flow
```
File Upload → Size Check → Extension Check → Content Validation → Filename Sanitization → Storage
     ↓              ↓              ↓               ↓                    ↓
  Reject       Reject        Reject          Sanitize            Safe Storage
```

#### Input Processing Security
```
User Input → Type Validation → Content Sanitization → Length Check → Processing
     ↓              ↓                  ↓                ↓
  Reject       Sanitize          Clean Input      Proceed Safely
```

## Performance and Scalability Context

### 1. Performance Optimization Strategies

#### Caching Architecture
- **Multi-level Caching**: Pipeline cache + LLM cache + Audio file cache
- **Cache Invalidation**: Time-based and content-based invalidation strategies
- **Memory Management**: Efficient DataFrame operations with pandas
- **Database Indexing**: Optimized SQLite queries for word lookups

#### Processing Optimization
- **Batch Operations**: Bulk database operations for efficiency
- **Parallel Processing**: Potential for concurrent transformation execution
- **Memory Usage**: Streaming processing for large word lists
- **I/O Optimization**: Minimized file system operations through caching

### 2. Scalability Considerations

#### Horizontal Scaling Potential
- **Stateless Design**: Each transformation is independent and stateless
- **Database Sharding**: Word-based sharding for distributed processing
- **Microservices Architecture**: Each transformation could be a separate service
- **Queue-based Processing**: Asynchronous processing for large workloads

#### Resource Management
- **File Size Limits**: Configurable limits prevent resource exhaustion
- **Processing Limits**: Word count limits prevent abuse
- **Memory Limits**: Efficient memory usage for large datasets
- **Timeout Controls**: Processing timeouts prevent infinite loops

## Integration Points for LLM Agents

### 1. Code Analysis Entry Points

#### Primary Analysis Targets
```python
# High-impact security components
src/ankineitor/security/validators.py      # Input validation logic
src/ankineitor/config/settings.py          # Configuration security
src/ankineitor/pipeline/llm_transformation.py  # AI integration security

# Core business logic
src/ankineitor/pipeline/pipeline.py        # Main processing orchestration
src/ankineitor/pipeline/transformations.py # Individual transformations
app/tabs/anki_tab.py                       # User interface security
```

#### Security-Specific Analysis Points
```python
# Critical security functions for detailed analysis
validate_file_upload()     # File upload security
sanitize_filename()        # Path traversal prevention  
validate_word_input()      # Input injection prevention
sanitize_sql_input()       # SQL injection prevention
```

### 2. AI Integration Analysis Context

#### LLM Usage Patterns for Analysis
```python
# Structured output generation patterns
sentence_chain = sentence_prompt | llm | sentence_parser
meaning_chain = meaning_prompt | llm | meaning_parser

# Prompt engineering patterns
Chinese prompts for Chinese word processing
Explicit JSON format requirements
Context preservation in example generation
```

#### Caching Strategy Analysis
```python
# Two-tier caching system analysis
pipeline_cache = SQLAlchemyClient("ankineitor_pipeline.db")
llm_cache = SQLAlchemyClient("ankineitor_llm_cache.db")

# Cache key design and invalidation strategies
cache_key = f"{word}:{transformation_type}:{language_pair}"
```

### 3. Configuration Analysis Context

#### Security Configuration
```python
# Environment-based configuration
Settings class with Pydantic validation
API key format validation: must start with "gsk_"
File size limits: 1-100 MB range
Log level validation: standard Python logging levels
```

#### Deployment Configuration
```python
# Docker-based deployment
Multi-stage builds for security
Non-root user execution
Volume mounting for data persistence
Environment variable injection
```

## Error Handling and Resilience Context

### 1. Error Handling Architecture

#### Layered Error Handling
```python
# Custom exception hierarchy
AnkineitorSecurityError (base)
├── InvalidFileError (file validation failures)
├── ValidationError (input validation failures)  
├── PathTraversalError (security violations)
└── SQLInjectionError (injection attempts)
```

#### Graceful Degradation Patterns
```python
# Fallback mechanisms for AI service failures
if llm_result is None:
    return cached_result or default_result

# Retry logic with exponential backoff
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def api_call_with_retry():
    # API call implementation
```

### 2. Logging and Monitoring Context

#### Security Event Logging
```python
# Security-focused logging
logger.info(f"File validation passed: {filename} ({size:.1f}MB)")
logger.warning(f"Suspicious characters detected: {content}")
logger.error(f"Security validation failed: {error}")
```

#### Performance Monitoring
```python
# Processing time tracking
with timer("pipeline_processing"):
    result = pipeline.transform_data(words)
    
# Cache hit/miss tracking
cache_stats = {"hits": 0, "misses": 0, "errors": 0}
```

## Conclusion for LLM Analysis

This architecture provides a robust, secure, and scalable foundation for AI-powered language learning automation. The system demonstrates best practices in:

1. **Security-First Design**: Multi-layer validation and sanitization
2. **AI Integration**: Structured LLM usage with caching and cost optimization
3. **User Experience**: Intuitive web interface with comprehensive error handling
4. **Scalability**: Efficient caching and processing optimization
5. **Maintainability**: Modular architecture with clear separation of concerns

The codebase is well-structured for LLM agent analysis, with clear entry points for security review, AI integration assessment, and architectural evaluation. The comprehensive test suite provides confidence in the system's reliability and security posture.
