#include "queue-analyzer.h"

namespace ns3 {

void QueueAnalyzer::ProcessTraceFile(std::string filename) {
  std::ifstream file(filename);
  std::string line;
  
  if (!file.is_open()) {
    std::cerr << "Cannot open file: " << filename << std::endl;
    return;
  }
  
  while (std::getline(file, line)) {
    std::istringstream iss(line);
    std::string token;
    std::vector<std::string> tokens;
    
    while (std::getline(iss, token, ',')) {
      tokens.push_back(token);
    }
    
    if (tokens.size() >= 3) {
      double time = std::stod(tokens[0]);
      std::string event = tokens[1];
      
      if (event == "ENQUEUE") {
        uint32_t packetId = std::stoul(tokens[2]);
        packetEnqueueTime[packetId] = time;
      }
      else if (event == "DEQUEUE") {
        uint32_t packetId = std::stoul(tokens[2]);
        if (packetEnqueueTime.find(packetId) != packetEnqueueTime.end()) {
          double delay = time - packetEnqueueTime[packetId];
          queueDelays.push_back(delay);
          packetEnqueueTime.erase(packetId);
        }
      }
      else if (event == "DROP") {
        totalDrops++;
      }
      else if (event == "QUEUE_LENGTH") {
        uint32_t newLength = std::stoul(tokens[3]);
        queueLengths.push_back(newLength);
      }
    }
  }
  file.close();
}

void QueueAnalyzer::PrintStatistics() {
  // Calculate average queue delay
  double avgDelay = 0;
  if (!queueDelays.empty()) {
    for (double delay : queueDelays) {
      avgDelay += delay;
    }
    avgDelay /= queueDelays.size();
  }
  
  // Calculate average queue length
  double avgQueueLength = 0;
  if (!queueLengths.empty()) {
    for (uint32_t length : queueLengths) {
      avgQueueLength += length;
    }
    avgQueueLength /= queueLengths.size();
  }
  
  std::cout << "=== Queue statistics ===" << std::endl;
  std::cout << "Average queue delay: " << avgDelay << " seconds" << std::endl;
  std::cout << "Average queue length: " << avgQueueLength << " packets" << std::endl;
  std::cout << "Total dropped packets: " << totalDrops << std::endl;
  std::cout << "Processed packets: " << queueDelays.size() << std::endl;
}

} // namespace ns3