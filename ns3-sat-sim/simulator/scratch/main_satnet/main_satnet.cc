/*
 * Copyright (c) 2020 ETH Zurich
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation;
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
 *
 * Author: Simon               2020
 */

#include <map>
#include <iostream>
#include <fstream>
#include <string>
#include <ctime>
#include <iostream>
#include <fstream>
#include <sys/stat.h>
#include <dirent.h>
#include <unistd.h>
#include <chrono>
#include <stdexcept>
#include <cstdlib> // for system()

#include "ns3/basic-simulation.h"
#include "ns3/tcp-flow-scheduler.h"
#include "ns3/udp-burst-scheduler.h"
#include "ns3/pingmesh-scheduler.h"
#include "ns3/topology-satellite-network.h"
#include "ns3/tcp-optimizer.h"
#include "ns3/arbiter-single-forward-helper.h"
#include "ns3/ipv4-arbiter-routing-helper.h"
#include "ns3/gsl-if-bandwidth-helper.h"
#include "ns3/queue-analyzer.h"

using namespace ns3;

int main(int argc, char *argv[]) {

    // No buffering of printf
    setbuf(stdout, nullptr);

    // Retrieve run directory
    CommandLine cmd;
    std::string run_dir = "";
    cmd.Usage("Usage: ./waf --run=\"main_satnet --run_dir='<path/to/run/directory>'\"");
    cmd.AddValue("run_dir",  "Run directory", run_dir);
    cmd.Parse(argc, argv);
    if (run_dir.compare("") == 0) {
        printf("Usage: ./waf --run=\"main_satnet --run_dir='<path/to/run/directory>'\"");
        return 0;
    }

    // Load basic simulation environment
    Ptr<BasicSimulation> basicSimulation = CreateObject<BasicSimulation>(run_dir);

    // Setting socket type
    Config::SetDefault ("ns3::TcpL4Protocol::SocketType", StringValue ("ns3::" + basicSimulation->GetConfigParamOrFail("tcp_socket_type")));

    // Optimize TCP
    TcpOptimizer::OptimizeBasic(basicSimulation);

    // Read topology, and install routing arbiters
    Ptr<TopologySatelliteNetwork> topology = CreateObject<TopologySatelliteNetwork>(basicSimulation, Ipv4ArbiterRoutingHelper());
    ArbiterSingleForwardHelper arbiterHelper(basicSimulation, topology->GetNodes());
    GslIfBandwidthHelper gslIfBandwidthHelper(basicSimulation, topology->GetNodes());
    
    // Schedule flows
    TcpFlowScheduler tcpFlowScheduler(basicSimulation, topology); // Requires enable_tcp_flow_scheduler=true

    // Schedule UDP bursts
    UdpBurstScheduler udpBurstScheduler(basicSimulation, topology); // Requires enable_udp_burst_scheduler=true

    // Schedule pings
    PingmeshScheduler pingmeshScheduler(basicSimulation, topology); // Requires enable_pingmesh_scheduler=true

    // ========== 動態閉環控制：分步執行模擬 ==========
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "DYNAMIC CLOSED-LOOP CONTROL MODE" << std::endl;
    std::cout << "========================================\n" << std::endl;

    // 讀取配置參數
    int64_t simulation_end_time_ns = basicSimulation->GetSimulationEndTimeNs();
    int64_t dynamic_state_update_interval_ns = 
        parse_positive_int64(basicSimulation->GetConfigParamOrFail("dynamic_state_update_interval_ns"));
    
    // 步長（以秒為單位）
    double step_size_s = dynamic_state_update_interval_ns / 1e9;
    
    std::cout << "Simulation parameters:" << std::endl;
    std::cout << "  > Total duration......... " << (simulation_end_time_ns / 1e9) << " s" << std::endl;
    std::cout << "  > Step size.............. " << step_size_s << " s (" 
              << (dynamic_state_update_interval_ns / 1e6) << " ms)" << std::endl;
    std::cout << "  > Total steps............ " 
              << (simulation_end_time_ns / dynamic_state_update_interval_ns) << std::endl;
    std::cout << std::endl;

    // 獲取 Python 腳本路徑
    std::string python_script_path = "../../../calculate_routes.py";

    // 獲取動態狀態算法名稱
    std::string dynamic_state_algorithm = basicSimulation->GetConfigParamOrFail("dynamic_state_algorithm");
    std::cout << "Using dynamic state calculation algorithm: " << dynamic_state_algorithm << std::endl << std::endl;

    // 迭代計數器
    int64_t current_time_ns = 0;
    int iteration = 0;
    
    // 主迴圈：分步執行模擬
    while (current_time_ns < simulation_end_time_ns) {
        
        std::cout << "========================================" << std::endl;
        std::cout << "Iteration " << iteration << ": t = " << (current_time_ns / 1e9) << " s" << std::endl;
        std::cout << "========================================" << std::endl;
        
        // 計算下一個時間點
        int64_t next_time_ns = current_time_ns + dynamic_state_update_interval_ns;
        if (next_time_ns > simulation_end_time_ns) {
            next_time_ns = simulation_end_time_ns;
        }
        
        // ===== 步驟 1: 執行一個時間步的模擬 =====
        std::cout << "\n[Step 1] Running simulation from " 
                  << (current_time_ns / 1e9) << "s to " 
                  << (next_time_ns / 1e9) << "s..." << std::endl;
        
        // 設定停止時間（覆蓋之前的設定）
        Simulator::Stop(NanoSeconds(dynamic_state_update_interval_ns - 1));
        
        // 執行模擬
        Simulator::Run();
        
        std::cout << "  > Simulation step completed at " 
                  << (Simulator::Now().GetNanoSeconds() / 1e9) << "s" << std::endl;
        
        // ===== 步驟 2: 輸出 Queue 統計數據 =====
        std::cout << "\n[Step 2] Writing ISL/GSL queue tracking results..." << std::endl;
        topology->WriteISLQueueTrackingResults();
        std::cout << "  > Queue data written to logs_ns3/{isl,gsl}_queue_pkt.csv" << std::endl;
        
        // ===== 步驟 3: 重置 Queue Trackers =====
        std::cout << "\n[Step 3] Resetting queue trackers for next iteration..." << std::endl;
        topology->ResetQueueTrackers();
        std::cout << "  > Queue trackers reset" << std::endl;
        
        // 更新當前時間
        current_time_ns = next_time_ns;
        
        // ===== 步驟 4: 如果還沒結束，呼叫 Python 計算下一個路由 =====
        if (current_time_ns < simulation_end_time_ns) {
            std::cout << "\n[Step 4] Calling Python script to calculate next routing..." << std::endl;
            
            // 構建 Python 命令
            std::ostringstream python_cmd;
            python_cmd << "cd " << run_dir << " && ";
            python_cmd << "python " << python_script_path;
            python_cmd << " --run_dir " << ".";
            python_cmd << " --fstate_calculation_algorithm " << dynamic_state_algorithm;
            python_cmd << " --current_time_ns " << current_time_ns;
            python_cmd << " --iteration " << iteration;
            
            std::string cmd_str = python_cmd.str();
            std::cout << "  > Executing: " << cmd_str << std::endl;
            
            // 執行 Python 腳本
            int ret = std::system(cmd_str.c_str());
            
            if (ret != 0) {
                std::cerr << "ERROR: Python script failed with return code " << ret << std::endl;
                // 可以選擇繼續或中止
                // throw std::runtime_error("Python routing calculation failed");
            } else {
                std::cout << "Python script finished without errors" << std::endl;
                std::cout << "New fstate file should be ready: fstate_" 
                          << current_time_ns << ".txt" << std::endl;
            }
            
            // 注意：ArbiterSingleForwardHelper 已經有排程事件會自動讀取新的 fstate
            // 所以這裡不需要手動觸發更新
            
        } else {
            std::cout << "\n[Final] Reached simulation end time, skipping route calculation" << std::endl;
        }
        
        iteration++;
        std::cout << "\nIteration " << (iteration - 1) << " completed!\n" << std::endl;
    }
    
    std::cout << "========================================" << std::endl;
    std::cout << "ALL ITERATIONS COMPLETED" << std::endl;
    std::cout << "========================================\n" << std::endl;
    
    // ===== 最終結果輸出 =====

    std::cout << "WRITING FINAL RESULTS" << std::endl;

    // Write flow results
    std::cout << "  > Writing TCP flow results..." << std::endl;
    tcpFlowScheduler.WriteResults();

    // Write UDP burst results
    std::cout << "  > Writing UDP burst results..." << std::endl;
    udpBurstScheduler.WriteResults();

    // Write pingmesh results
    std::cout << "  > Writing pingmesh results..." << std::endl;
    pingmeshScheduler.WriteResults();

    // Collect utilization statistics
    std::cout << "  > Collecting utilization statistics..." << std::endl;
    topology->CollectUtilizationStatistics();

    std::cout << "  > All results written" << std::endl;
    std::cout << std::endl;

    // Finalize the simulation
    basicSimulation->Finalize();

    return 0;

}
