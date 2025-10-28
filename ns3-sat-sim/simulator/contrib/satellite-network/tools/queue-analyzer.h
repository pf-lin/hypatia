#ifndef QUEUE_ANALYZER_H
#define QUEUE_ANALYZER_H

#include <map>
#include <vector>
#include <string>
#include <fstream>
#include <sstream>
#include <iostream>
#include "ns3/core-module.h"

namespace ns3 {

class QueueAnalyzer {
public:
  QueueAnalyzer() : totalDrops(0) {}
  void ProcessTraceFile(std::string filename);
  void PrintStatistics();
  
private:
  std::map<uint32_t, double> packetEnqueueTime;  // Packet enqueue time (封包入隊時間)
  std::vector<double> queueDelays;               // Queue delays (隊列延遲)
  uint32_t totalDrops;                           // Total dropped packets (總丟包數)
  std::vector<uint32_t> queueLengths;            // Queue lengths (隊列長度歷史)
};

} // namespace ns3

#endif /* QUEUE_ANALYZER_H */