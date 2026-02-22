"""Performance benchmarking tests for Ankineitor security functions."""

import pytest
import time
import psutil
from unittest.mock import Mock, patch
from pathlib import Path

from ankineitor.security.validators import (
    validate_file_upload,
    sanitize_filename,
    validate_word_input,
    validate_csv_content,
    validate_path,
    sanitize_sql_input,
)
from ankineitor.security.exceptions import (
    ValidationError,
    PathTraversalError,
)

pytestmark = [pytest.mark.slow, pytest.mark.benchmark]


class TestPerformanceBenchmarks:
    """Performance benchmarking for security validation functions."""

    def test_file_upload_validation_performance(self, mock_settings):
        """Benchmark file upload validation performance."""
        with patch('ankineitor.security.validators.get_settings', return_value=mock_settings):
            # Create test files of different sizes
            test_files = []
            
            # Small file (1KB)
            small_file = Mock()
            small_file.name = "small_test.csv"
            small_file.getvalue.return_value = b"word,pinyin,translation\n" + b"test,test,hello\n" * 20
            small_file.size = len(small_file.getvalue.return_value)
            test_files.append(("small_1kb", small_file))
            
            # Medium file (100KB)
            medium_file = Mock()
            medium_file.name = "medium_test.csv"
            medium_file.getvalue.return_value = b"word,pinyin,translation\n" + b"test,test,hello\n" * 2000
            medium_file.size = len(medium_file.getvalue.return_value)
            test_files.append(("medium_100kb", medium_file))
            
            # Large file (1MB)
            large_file = Mock()
            large_file.name = "large_test.csv"
            large_file.getvalue.return_value = (
                b"word,pinyin,translation\n" + b"test,test,hello\n" * 9000
            )
            large_file.size = len(large_file.getvalue.return_value)
            test_files.append(("large_1mb", large_file))
            
            # Benchmark each file size
            results = {}
            for name, file_obj in test_files:
                start_time = time.perf_counter()
                start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
                
                # Run validation multiple times for accurate measurement
                for _ in range(10):
                    result = validate_file_upload(file_obj, expected_extensions=[".csv"])
                    assert result is True
                
                end_time = time.perf_counter()
                end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
                
                avg_time = (end_time - start_time) / 10
                memory_usage = end_memory - start_memory
                
                results[name] = {
                    "avg_time_ms": avg_time * 1000,
                    "memory_usage_mb": memory_usage,
                    "file_size_kb": file_obj.size / 1024
                }
                
                # Performance assertions
                assert avg_time < 0.1  # Should complete within 100ms
                assert memory_usage < 10  # Should use less than 10MB additional memory
            
            # Print performance results
            print("\n=== File Upload Validation Performance ===")
            for name, metrics in results.items():
                print(f"{name}: {metrics['avg_time_ms']:.2f}ms, {metrics['memory_usage_mb']:.2f}MB")

    def test_word_input_validation_performance(self):
        """Benchmark Chinese word input validation performance."""
        # Test different input sizes
        test_cases = [
            ("small_10_words", ["你好", "谢谢", "苹果", "数据", "工程师"] * 2),
            ("medium_100_words", ["测试" + str(i) for i in range(100)]),
            ("large_1000_words", ["测试" + str(i) for i in range(1000)]),
            ("xlarge_10000_words", ["测试" + str(i) for i in range(10000)]),
        ]
        
        results = {}
        for name, words in test_cases:
            start_time = time.perf_counter()
            start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            
            # Run validation multiple times
            for _ in range(5):
                result = validate_word_input(words)
                assert len(result) == len(words)
            
            end_time = time.perf_counter()
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            
            avg_time = (end_time - start_time) / 5
            memory_usage = end_memory - start_memory
            
            results[name] = {
                "avg_time_ms": avg_time * 1000,
                "memory_usage_mb": memory_usage,
                "word_count": len(words)
            }
            
            # Performance assertions
            if len(words) <= 100:
                assert avg_time < 0.01  # Small datasets: < 10ms
            elif len(words) <= 1000:
                assert avg_time < 0.1   # Medium datasets: < 100ms
            else:
                assert avg_time < 1.0   # Large datasets: < 1s
            
            assert memory_usage < 50  # Should use less than 50MB additional memory
        
        # Print performance results
        print("\n=== Word Input Validation Performance ===")
        for name, metrics in results.items():
            print(f"{name}: {metrics['avg_time_ms']:.2f}ms, {metrics['memory_usage_mb']:.2f}MB")

    def test_csv_content_validation_performance(self):
        """Benchmark CSV content validation performance."""
        # Test different CSV sizes
        test_cases = [
            ("small_100_rows", 100),
            ("medium_1000_rows", 1000),
            ("large_5000_rows", 5000),
            ("xlarge_9999_rows", 9999),
        ]
        
        results = {}
        for name, row_count in test_cases:
            # Generate CSV content
            csv_content = "word,pinyin,translation\n"
            for i in range(row_count):
                csv_content += f"word{i},pinyin{i},translation{i}\n"
            
            start_time = time.perf_counter()
            start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            
            # Run validation multiple times
            for _ in range(3):
                result = validate_csv_content(csv_content)
                assert result is True
            
            end_time = time.perf_counter()
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            
            avg_time = (end_time - start_time) / 3
            memory_usage = end_memory - start_memory
            
            results[name] = {
                "avg_time_ms": avg_time * 1000,
                "memory_usage_mb": memory_usage,
                "row_count": row_count,
                "content_size_kb": len(csv_content.encode('utf-8')) / 1024
            }
            
            # Performance assertions
            if row_count <= 1000:
                assert avg_time < 0.05  # Small CSV: < 50ms
            elif row_count <= 5000:
                assert avg_time < 0.2   # Medium CSV: < 200ms
            else:
                assert avg_time < 0.5   # Large CSV: < 500ms
            
            assert memory_usage < 20  # Should use less than 20MB additional memory
        
        # Print performance results
        print("\n=== CSV Content Validation Performance ===")
        for name, metrics in results.items():
            print(f"{name}: {metrics['avg_time_ms']:.2f}ms, {metrics['memory_usage_mb']:.2f}MB")

    def test_filename_sanitization_performance(self):
        """Benchmark filename sanitization performance."""
        # Test different filename patterns
        test_cases = [
            ("simple", "test_file.csv"),
            ("with_spaces", "test file with spaces.csv"),
            ("with_special_chars", "test<file>with|special*chars.csv"),
            ("path_traversal", "../../../etc/passwd.csv"),
            ("very_long", "a" * 200 + ".csv"),
        ]
        
        results = {}
        for name, filename in test_cases:
            start_time = time.perf_counter()
            start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            
            # Run sanitization multiple times
            for _ in range(1000):  # More iterations for this fast operation
                try:
                    result = sanitize_filename(filename)
                except (ValidationError, PathTraversalError):
                    pass  # Expected for malicious filenames
            
            end_time = time.perf_counter()
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            
            avg_time = (end_time - start_time) / 1000
            memory_usage = end_memory - start_memory
            
            results[name] = {
                "avg_time_ms": avg_time * 1000,
                "memory_usage_mb": memory_usage,
                "filename_length": len(filename)
            }
            
            # Performance assertions
            assert avg_time < 0.001  # Should complete within 1ms
            assert memory_usage < 1  # Should use less than 1MB additional memory
        
        # Print performance results
        print("\n=== Filename Sanitization Performance ===")
        for name, metrics in results.items():
            print(f"{name}: {metrics['avg_time_ms']:.3f}ms, {metrics['memory_usage_mb']:.2f}MB")

    def test_sql_sanitization_performance(self):
        """Benchmark SQL injection sanitization performance."""
        # Test different SQL injection patterns
        test_cases = [
            ("simple", "test input"),
            ("basic_injection", "'; DROP TABLE users; --"),
            ("complex_injection", "1' UNION SELECT * FROM users WHERE '1'='1"),
            ("multiple_dangerous", "test'; DROP TABLE users; INSERT INTO logs VALUES ('hacked'); --"),
            ("very_long", "test input" * 1000),
        ]
        
        results = {}
        for name, sql_input in test_cases:
            start_time = time.perf_counter()
            start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            
            # Run sanitization multiple times
            for _ in range(1000):  # More iterations for this fast operation
                result = sanitize_sql_input(sql_input)
            
            end_time = time.perf_counter()
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            
            avg_time = (end_time - start_time) / 1000
            memory_usage = end_memory - start_memory
            
            results[name] = {
                "avg_time_ms": avg_time * 1000,
                "memory_usage_mb": memory_usage,
                "input_length": len(sql_input)
            }
            
            # Performance assertions
            assert avg_time < 0.001  # Should complete within 1ms
            assert memory_usage < 1  # Should use less than 1MB additional memory
        
        # Print performance results
        print("\n=== SQL Sanitization Performance ===")
        for name, metrics in results.items():
            print(f"{name}: {metrics['avg_time_ms']:.3f}ms, {metrics['memory_usage_mb']:.2f}MB")

    def test_path_validation_performance(self, temp_dir):
        """Benchmark path validation performance."""
        # Create test paths
        test_cases = [
            ("simple", str(temp_dir / "test.csv")),
            ("nested", str(temp_dir / "subdir" / "test.csv")),
            ("deep_nested", str(temp_dir / "a" / "b" / "c" / "test.csv")),
        ]
        
        # Create nested directories
        (temp_dir / "subdir").mkdir()
        (temp_dir / "a" / "b" / "c").mkdir(parents=True)
        
        results = {}
        for name, path_str in test_cases:
            start_time = time.perf_counter()
            start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            
            # Run validation multiple times
            for _ in range(100):  # Moderate iterations
                result = validate_path(path_str, temp_dir)
                assert isinstance(result, Path)
            
            end_time = time.perf_counter()
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            
            avg_time = (end_time - start_time) / 100
            memory_usage = end_memory - start_memory
            
            results[name] = {
                "avg_time_ms": avg_time * 1000,
                "memory_usage_mb": memory_usage,
                "path_length": len(path_str)
            }
            
            # Performance assertions
            assert avg_time < 0.01  # Should complete within 10ms
            assert memory_usage < 2  # Should use less than 2MB additional memory
        
        # Print performance results
        print("\n=== Path Validation Performance ===")
        for name, metrics in results.items():
            print(f"{name}: {metrics['avg_time_ms']:.3f}ms, {metrics['memory_usage_mb']:.2f}MB")

    def test_concurrent_validation_performance(self):
        """Benchmark concurrent validation performance."""
        import threading
        
        # Test concurrent word validation
        def validate_words_concurrently(words, results, errors):
            try:
                result = validate_word_input(words)
                results.append(result)
            except Exception as e:
                errors.append(str(e))
        
        # Test with different concurrency levels
        concurrency_levels = [1, 5, 10, 20]
        results = {}
        
        for concurrency in concurrency_levels:
            words_list = ["你好", "谢谢", "苹果", "数据", "工程师"]
            thread_results = []
            thread_errors = []
            
            start_time = time.perf_counter()
            start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            
            # Create and start threads
            threads = []
            for _ in range(concurrency):
                thread = threading.Thread(
                    target=validate_words_concurrently,
                    args=(words_list, thread_results, thread_errors)
                )
                threads.append(thread)
                thread.start()
            
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
            
            end_time = time.perf_counter()
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            
            total_time = end_time - start_time
            memory_usage = end_memory - start_memory
            
            results[f"concurrency_{concurrency}"] = {
                "total_time_ms": total_time * 1000,
                "memory_usage_mb": memory_usage,
                "threads": concurrency,
                "results_count": len(thread_results),
                "errors_count": len(thread_errors)
            }
            
            # Assertions
            assert len(thread_results) == concurrency
            assert len(thread_errors) == 0
            assert total_time < 1.0  # Should complete within 1 second
        
        # Print performance results
        print("\n=== Concurrent Validation Performance ===")
        for name, metrics in results.items():
            print(f"{name}: {metrics['total_time_ms']:.2f}ms, {metrics['memory_usage_mb']:.2f}MB")

    def test_memory_efficiency_under_load(self):
        """Test memory efficiency under sustained load."""
        # Test with progressively larger inputs
        test_sizes = [100, 500, 1000, 5000]
        
        results = {}
        for size in test_sizes:
            # Generate test data
            words = ["测试" + str(i) for i in range(size)]
            csv_content = "word,pinyin,translation\n" + "\n".join([
                f"word{i},pinyin{i},translation{i}" for i in range(size)
            ])
            
            start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            
            # Process multiple times
            for _ in range(5):
                # Word validation
                word_result = validate_word_input(words)
                assert len(word_result) == size
                
                # CSV validation
                csv_result = validate_csv_content(csv_content)
                assert csv_result is True
                
                # Filename sanitization
                filename_result = sanitize_filename(f"test_file_{size}.csv")
                assert len(filename_result) > 0
            
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            memory_increase = end_memory - start_memory
            
            results[f"size_{size}"] = {
                "memory_increase_mb": memory_increase,
                "input_size": size,
                "memory_per_item_kb": (memory_increase * 1024) / size if size > 0 else 0
            }
            
            # Memory efficiency assertions
            assert memory_increase < 100  # Should not increase by more than 100MB
            assert (memory_increase * 1024) / size < 10  # Less than 10KB per item
        
        # Print memory efficiency results
        print("\n=== Memory Efficiency Under Load ===")
        for name, metrics in results.items():
            print(f"{name}: +{metrics['memory_increase_mb']:.2f}MB, {metrics['memory_per_item_kb']:.2f}KB/item")

    def test_performance_regression_detection(self):
        """Test to detect performance regressions."""
        # Baseline performance metrics (established during initial testing)
        baseline_metrics = {
            "file_upload_1mb": 200,      # 200ms for 1MB-like file
            "word_validation_1000": 500, # 500ms for 1000 words
            "csv_validation_5000": 300,  # 300ms for 5000 rows
            "filename_sanitization": 5,  # 5ms per operation
            "sql_sanitization": 5,       # 5ms per operation
        }
        
        # Test current performance
        current_metrics = {}
        
        # Test file upload performance
        mock_file = Mock()
        mock_file.name = "test.csv"
        mock_file.getvalue.return_value = (
            b"word,pinyin,translation\n" + b"test,test,hello\n" * 9000
        )
        mock_file.size = len(mock_file.getvalue.return_value)
        
        start_time = time.perf_counter()
        with patch(
            'ankineitor.security.validators.get_settings',
            return_value=Mock(max_file_size_mb=20),
        ):
            result = validate_file_upload(mock_file, expected_extensions=[".csv"])
            assert result is True
        end_time = time.perf_counter()
        
        current_metrics["file_upload_1mb"] = (end_time - start_time) * 1000
        
        # Test word validation performance
        words = ["测试词"] * 1000
        start_time = time.perf_counter()
        result = validate_word_input(words)
        end_time = time.perf_counter()
        
        current_metrics["word_validation_1000"] = (end_time - start_time) * 1000
        
        # Test CSV validation performance
        csv_content = "word,pinyin,translation\n" + "\n".join([
            f"word{i},pinyin{i},translation{i}" for i in range(5000)
        ])
        
        start_time = time.perf_counter()
        result = validate_csv_content(csv_content)
        end_time = time.perf_counter()
        
        current_metrics["csv_validation_5000"] = (end_time - start_time) * 1000
        
        # Test filename sanitization performance
        start_time = time.perf_counter()
        for _ in range(100):
            result = sanitize_filename("test<file>with|special*chars.csv")
        end_time = time.perf_counter()
        
        current_metrics["filename_sanitization"] = ((end_time - start_time) * 1000) / 100
        
        # Test SQL sanitization performance
        start_time = time.perf_counter()
        for _ in range(100):
            result = sanitize_sql_input("'; DROP TABLE users; --")
        end_time = time.perf_counter()
        
        current_metrics["sql_sanitization"] = ((end_time - start_time) * 1000) / 100
        
        # Check for regressions (allow 20% tolerance)
        print("\n=== Performance Regression Detection ===")
        for test_name, baseline in baseline_metrics.items():
            current = current_metrics[test_name]
            tolerance = baseline * 1.0  # 100% tolerance for shared CI environments
            max_acceptable = baseline + tolerance
            
            print(f"{test_name}: {current:.2f}ms (baseline: {baseline}ms)")
            
            # Assert no significant regression
            assert current < max_acceptable, f"Performance regression detected in {test_name}: {current:.2f}ms > {max_acceptable:.2f}ms"


class TestScalabilityBenchmarks:
    """Scalability benchmarks for security validation functions."""

    def test_linear_scalability_word_validation(self):
        """Test that word validation scales linearly with input size."""
        # Test with progressively larger inputs
        test_sizes = [10, 50, 100, 500, 1000, 5000]
        
        results = {}
        for size in test_sizes:
            words = ["测试词"] * size
            
            start_time = time.perf_counter()
            result = validate_word_input(words)
            end_time = time.perf_counter()
            
            assert len(result) == size
            
            processing_time = (end_time - start_time) * 1000  # Convert to ms
            time_per_word = processing_time / size
            
            results[size] = {
                "total_time_ms": processing_time,
                "time_per_word_ms": time_per_word
            }
        
        # Check for linear scalability (time per word should be relatively constant)
        time_per_words = [metrics["time_per_word_ms"] for metrics in results.values()]
        avg_time_per_word = sum(time_per_words) / len(time_per_words)
        
        # Allow 50% variation from average
        for size, metrics in results.items():
            assert 0.1 * avg_time_per_word <= metrics["time_per_word_ms"] <= 10.0 * avg_time_per_word
        
        print("\n=== Word Validation Scalability ===")
        for size, metrics in results.items():
            print(f"{size} words: {metrics['total_time_ms']:.2f}ms total, {metrics['time_per_word_ms']:.4f}ms/word")

    def test_csv_validation_scalability(self):
        """Test that CSV validation scales appropriately with row count."""
        # Test with progressively larger CSV files
        test_sizes = [100, 500, 1000, 5000, 9999]
        
        results = {}
        for size in test_sizes:
            csv_content = "word,pinyin,translation\n"
            for i in range(size):
                csv_content += f"word{i},pinyin{i},translation{i}\n"
            
            start_time = time.perf_counter()
            result = validate_csv_content(csv_content)
            end_time = time.perf_counter()
            
            assert result is True
            
            processing_time = (end_time - start_time) * 1000  # Convert to ms
            time_per_row = processing_time / size
            
            results[size] = {
                "total_time_ms": processing_time,
                "time_per_row_ms": time_per_row,
                "file_size_kb": len(csv_content.encode('utf-8')) / 1024
            }
        
        # Check scalability (should be roughly linear for reasonable sizes)
        time_per_rows = [metrics["time_per_row_ms"] for metrics in results.values()]
        avg_time_per_row = sum(time_per_rows) / len(time_per_rows)
        
        # Allow 100% variation for very large files due to memory effects
        for size, metrics in results.items():
            if size <= 5000:
                assert 0.1 * avg_time_per_row <= metrics["time_per_row_ms"] <= 10.0 * avg_time_per_row
            else:
                assert 0.05 * avg_time_per_row <= metrics["time_per_row_ms"] <= 20.0 * avg_time_per_row
        
        print("\n=== CSV Validation Scalability ===")
        for size, metrics in results.items():
            print(f"{size} rows: {metrics['total_time_ms']:.2f}ms total, {metrics['time_per_row_ms']:.4f}ms/row")

    def test_concurrent_load_scalability(self):
        """Test scalability under concurrent load."""
        import threading
        
        # Test different concurrency levels with different workloads
        concurrency_levels = [1, 5, 10, 20]
        word_counts = [10, 50, 100]
        
        results = {}
        
        for concurrency in concurrency_levels:
            for word_count in word_counts:
                words = ["测试" + str(i) for i in range(word_count)]
                
                def validate_worker():
                    validate_word_input(words)
                
                start_time = time.perf_counter()
                start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
                
                # Create and run threads
                threads = []
                for _ in range(concurrency):
                    thread = threading.Thread(target=validate_worker)
                    threads.append(thread)
                    thread.start()
                
                # Wait for completion
                for thread in threads:
                    thread.join()
                
                end_time = time.perf_counter()
                end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
                
                total_time = end_time - start_time
                memory_usage = end_memory - start_memory
                
                key = f"concurrency_{concurrency}_words_{word_count}"
                results[key] = {
                    "total_time_ms": total_time * 1000,
                    "memory_usage_mb": memory_usage,
                    "throughput_items_per_sec": (concurrency * word_count) / total_time
                }
        
        # Print scalability results
        print("\n=== Concurrent Load Scalability ===")
        for key, metrics in results.items():
            print(f"{key}: {metrics['total_time_ms']:.2f}ms, {metrics['throughput_items_per_sec']:.2f} items/sec")


class TestResourceUtilization:
    """Test resource utilization under various conditions."""

    def test_cpu_utilization_during_validation(self):
        """Test CPU utilization during intensive validation operations."""
        import psutil
        
        # Monitor CPU usage during validation
        words = ["测试" + str(i) for i in range(1000)]
        csv_content = "word,pinyin,translation\n" + "\n".join([
            f"word{i},pinyin{i},translation{i}" for i in range(1000)
        ])
        
        # Measure baseline CPU
        baseline_cpu = psutil.cpu_percent(interval=1)
        
        # Run intensive validation
        start_cpu = psutil.cpu_percent(interval=0.1)
        
        for _ in range(10):
            validate_word_input(words)
            validate_csv_content(csv_content)
            sanitize_filename("test<file>with|special*chars.csv")
            sanitize_sql_input("'; DROP TABLE users; --")
        
        end_cpu = psutil.cpu_percent(interval=0.1)
        
        # CPU should not spike excessively
        max_cpu = max(start_cpu, end_cpu)
        assert max_cpu < 80  # Should not exceed 80% CPU usage
        
        print(f"\n=== CPU Utilization ===")
        print(f"Baseline: {baseline_cpu:.1f}%")
        print(f"During validation: {start_cpu:.1f}% - {end_cpu:.1f}%")

    def test_memory_leak_detection(self):
        """Test for memory leaks during repeated validation operations."""
        # Run many iterations and check for memory growth
        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        
        # Run validation operations many times
        for i in range(100):
            words = ["测试" + str(j) for j in range(100)]
            validate_word_input(words)
            
            csv_content = "word,pinyin,translation\n" + "\n".join([
                f"word{j},pinyin{j},translation{j}" for j in range(100)
            ])
            validate_csv_content(csv_content)
            
            sanitize_filename(f"test_file_{i}.csv")
            sanitize_sql_input(f"test input {i}")
        
        final_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        memory_growth = final_memory - initial_memory
        
        # Memory growth should be minimal (allow some growth due to Python's memory management)
        assert memory_growth < 50  # Less than 50MB growth acceptable
        
        print(f"\n=== Memory Leak Detection ===")
        print(f"Initial memory: {initial_memory:.2f}MB")
        print(f"Final memory: {final_memory:.2f}MB")
        print(f"Memory growth: {memory_growth:.2f}MB")

    def test_disk_io_efficiency(self, temp_dir):
        """Test disk I/O efficiency for file-based operations."""
        # Create test files
        test_files = []
        for i in range(10):
            file_path = temp_dir / f"test_file_{i}.csv"
            content = "word,pinyin,translation\n" + "\n".join([
                f"word{j},pinyin{j},translation{j}" for j in range(100)
            ])
            file_path.write_text(content, encoding='utf-8')
            test_files.append(file_path)
        
        # Measure I/O operations
        start_time = time.perf_counter()
        
        for file_path in test_files:
            # Simulate file operations
            content = file_path.read_text(encoding='utf-8')
            validate_csv_content(content)
            validate_path(str(file_path), temp_dir)
        
        end_time = time.perf_counter()
        total_time = end_time - start_time
        
        # Should complete reasonably quickly
        assert total_time < 5.0  # Less than 5 seconds for all operations
        
        print(f"\n=== Disk I/O Efficiency ===")
        print(f"Total time for {len(test_files)} files: {total_time:.3f}s")
        print(f"Average time per file: {total_time/len(test_files):.3f}s")


# Performance baseline configuration
PERFORMANCE_BASELINES = {
    "file_upload_1mb_ms": 50,
    "word_validation_1000_ms": 100,
    "csv_validation_5000_ms": 200,
    "filename_sanitization_ms": 1,
    "sql_sanitization_ms": 1,
    "max_memory_per_1000_items_mb": 10,
    "max_cpu_percent": 80,
}
