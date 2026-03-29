# test_network.py
import subprocess
import time

def test_ping(ip, count=10):
    print(f"\nTesting {ip} with {count} pings...")
    try:
        cmd = ["ping", "-c", str(count), ip]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Extract stats from output
        lines = result.stdout.split('\n')
        for line in lines:
            if 'avg' in line or 'rtt' in line:
                print(f"  {line}")
        
        # Count successes
        success_count = 0
        for line in lines:
            if 'time=' in line or 'time<' in line:
                success_count += 1
        
        loss = ((count - success_count) / count) * 100
        print(f"  Packet loss: {loss:.1f}%")
        
        return success_count > 0
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    print("Network Quality Test")
    print("="*50)
    
    test_ping("8.8.8.8", 20)  # Google DNS
    test_ping("1.1.1.1", 20)  # Cloudflare DNS
    test_ping("10.3.104.2", 10)  # Your gateway
